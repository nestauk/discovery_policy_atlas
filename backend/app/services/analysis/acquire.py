from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin
import re

import httpx
import pandas as pd

from app.core.config import settings
from .scrape import async_fetch_html
from .utils_paths import sanitize_id_to_filename


logger = logging.getLogger(__name__)


BROWSER_UAS = [
    # Deterministic rotation pool
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UAS[0],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class AcquisitionService:
    def __init__(self, export_dir: Optional[str] = None, timeout: float = 30.0):
        self.export_dir = Path(export_dir or settings.EXPORT_FILES_DIR)
        self.raw_dir = self.export_dir / "data" / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    async def acquire_all(
        self, references_csv: str, concurrency: int = 5
    ) -> List[Dict[str, str]]:
        df = pd.read_csv(references_csv)
        records = df.to_dict("records")

        sem = asyncio.Semaphore(concurrency)
        results: List[Dict[str, str]] = []
        failures: List[Dict[str, str]] = []

        async def _acquire_one(rec: Dict[str, str]):
            async with sem:
                try:
                    result = await self._download_document(rec)
                    if result and result.get("status") == "ok":
                        results.append(result)
                    else:
                        failures.append(
                            result or {"doc_id": rec.get("doc_id"), "status": "failed"}
                        )
                except Exception as e:
                    logger.warning(
                        "Acquisition failed for %s: %s", rec.get("doc_id"), e
                    )
                    failures.append(
                        {
                            "doc_id": rec.get("doc_id"),
                            "status": "exception",
                            "error": str(e),
                        }
                    )

        await asyncio.gather(*[_acquire_one(r) for r in records])

        # Write manifests
        manifest_dir = self.export_dir / "data"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        with (manifest_dir / "manifest.jsonl").open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with (manifest_dir / "manifest_failures.jsonl").open(
            "w", encoding="utf-8"
        ) as f:
            for r in failures:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        logger.info("Acquisition complete: %d documents", len(results))
        return results

    async def _download_document(self, rec: Dict[str, str]) -> Optional[Dict[str, str]]:
        source = (rec.get("source") or "").strip()
        doc_id = (rec.get("doc_id") or "").strip()
        pdf_url_val = rec.get("pdf_url")
        landing_url_val = rec.get("landing_page_url")
        doi_val = rec.get("doi")
        pdf_url = (
            str(pdf_url_val).strip() if isinstance(pdf_url_val, str) else None
        ) or None
        landing_url = (
            str(landing_url_val).strip() if isinstance(landing_url_val, str) else None
        ) or None
        doi_url = (str(doi_val).strip() if isinstance(doi_val, str) else None) or None
        # Normalize DOI to full URL if present
        if doi_url and not doi_url.lower().startswith("http"):
            doi_url = f"https://doi.org/{doi_url}"
        # If no explicit DOI URL but doc_id looks like a DOI or doi.org URL, use doc_id
        if not doi_url and source == "openalex":
            if doc_id.startswith("http") and "doi.org" in doc_id:
                doi_url = doc_id
            elif re.match(r"^10\.\d{4,9}/.+", doc_id):
                doi_url = f"https://doi.org/{doc_id}"

        if not doc_id:
            return None

        # Flat structure: single directory, filenames derived from doc_id (canonical)
        safe_base = sanitize_id_to_filename(doc_id)
        target_dir = self.raw_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Try PDF first
        if pdf_url:
            # If we have both a landing and a PDF (e.g., from OpenAlex best_oa_location), use the landing as referer
            kind, path = await self._try_fetch(
                pdf_url,
                target_dir,
                preferred_base=safe_base,
                referer=landing_url or doi_url,
            )
            if kind:
                return {
                    "doc_id": doc_id,
                    "source": source,
                    "file_type": kind,
                    "file_path": str(path),
                    "status": "ok",
                }

        # Fallback to landing page
        if landing_url:
            # Use scraper for robust HTML extraction
            try:
                html, _text = await async_fetch_html(landing_url, timeout=self.timeout)
                out_path = target_dir / f"{safe_base}.html"
                out_path.write_text(html, encoding="utf-8")
                if _text and _text.strip():
                    (target_dir / f"{safe_base}.txt").write_text(
                        _text, encoding="utf-8"
                    )
                # Try to discover a PDF link on the page and fetch it too (best-effort)
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(html, "lxml")
                    pdf_href = None
                    for a in soup.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue
                        if (
                            href.lower().endswith(".pdf")
                            or a.get("type") == "application/pdf"
                        ):
                            pdf_href = urljoin(landing_url, href)
                            break
                    # Regex fallback: look for any .pdf URL in raw HTML (handles JSON-in-HTML cases)
                    if not pdf_href:
                        match = re.search(
                            r"https?://[^\s'\"]+\.pdf", html, flags=re.IGNORECASE
                        )
                        if match:
                            pdf_href = match.group(0)
                    if pdf_href:
                        k2, p2 = await self._try_fetch(
                            pdf_href,
                            target_dir,
                            preferred_base=safe_base,
                            referer=landing_url,
                        )
                        if k2 == "pdf" and p2:
                            return {
                                "doc_id": doc_id,
                                "source": source,
                                "file_type": "pdf",
                                "file_path": str(p2),
                                "status": "ok",
                                "via": "found_pdf_link",
                            }
                except Exception:
                    pass
                return {
                    "doc_id": doc_id,
                    "source": source,
                    "file_type": "html",
                    "file_path": str(out_path),
                    "status": "ok",
                }
            except Exception:
                kind, path = await self._try_fetch(
                    landing_url, target_dir, preferred_base=safe_base
                )
                if kind:
                    return {
                        "doc_id": doc_id,
                        "source": source,
                        "file_type": kind,
                        "file_path": str(path),
                        "status": "ok",
                    }

        # Final fallback: try DOI URL (commonly a landing page). Scrape even if not a PDF
        if doi_url:
            try:
                html, _text = await async_fetch_html(doi_url, timeout=self.timeout)
                out_path = target_dir / f"{safe_base}.html"
                out_path.write_text(html, encoding="utf-8")
                if _text and _text.strip():
                    (target_dir / f"{safe_base}.txt").write_text(
                        _text, encoding="utf-8"
                    )
                # Attempt to locate a PDF link
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(html, "lxml")
                    pdf_href = None
                    for a in soup.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue
                        if (
                            href.lower().endswith(".pdf")
                            or a.get("type") == "application/pdf"
                        ):
                            pdf_href = urljoin(doi_url, href)
                            break
                    if not pdf_href:
                        match = re.search(
                            r"https?://[^\s'\"]+\.pdf", html, flags=re.IGNORECASE
                        )
                        if match:
                            pdf_href = match.group(0)
                    if pdf_href:
                        k2, p2 = await self._try_fetch(
                            pdf_href,
                            target_dir,
                            preferred_base=safe_base,
                            referer=doi_url,
                        )
                        if k2 == "pdf" and p2:
                            return {
                                "doc_id": doc_id,
                                "source": source,
                                "file_type": "pdf",
                                "file_path": str(p2),
                                "status": "ok",
                                "via": "doi_pdf_link",
                            }
                except Exception:
                    pass
                # If we got meaningful text from DOI landing, return success with html
                if _text and len(_text.strip()) > 500:
                    return {
                        "doc_id": doc_id,
                        "source": source,
                        "file_type": "html",
                        "file_path": str(out_path),
                        "status": "ok",
                        "via": "doi_landing_rich",
                    }
                else:
                    # Still return basic html; downstream can flag likely paywall by short content length
                    return {
                        "doc_id": doc_id,
                        "source": source,
                        "file_type": "html",
                        "file_path": str(out_path),
                        "status": "ok",
                        "via": "doi_landing",
                    }
            except Exception:
                pass

        return {"doc_id": doc_id, "source": source, "status": "not_fetched"}

    async def _try_fetch(
        self,
        url: str,
        target_dir: Path,
        preferred_base: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Path]]:
        try:
            # Pick a UA deterministically by URL
            ua = BROWSER_UAS[hash(url) % len(BROWSER_UAS)]
            headers = DEFAULT_HEADERS | {"User-Agent": ua}
            if referer:
                headers["Referer"] = referer
            async with httpx.AsyncClient(
                timeout=self.timeout, headers=headers, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "").lower()
                if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                    base = preferred_base or sanitize_id_to_filename(url)
                    out_path = target_dir / f"{base}.pdf"
                    out_path.write_bytes(resp.content)
                    return "pdf", out_path
                else:
                    # Save HTML/text
                    base = preferred_base or sanitize_id_to_filename(url)
                    out_path = target_dir / f"{base}.html"
                    text = resp.text
                    out_path.write_text(text, encoding="utf-8")
                    return "html", out_path
        except httpx.HTTPStatusError as e:
            # If forbidden, return None for this URL; caller may still have HTML already scraped
            if e.response is not None and e.response.status_code in (401, 403):
                return None, None
            return None, None
        except Exception as e:
            logger.debug("Fetch failed for %s: %s", url, e)
            return None, None
