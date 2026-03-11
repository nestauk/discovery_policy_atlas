from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

from app.core.config import settings

try:
    from scrapling.fetchers import Fetcher  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Fetcher = None


logger = logging.getLogger(__name__)


class ParsingError(Exception):
    """Exception raised when parsing fails with a user-friendly message."""

    pass


def should_skip_large_pdf(
    file_size_bytes: int,
) -> tuple[bool, str | None]:
    """
    Check if a PDF should be skipped based on file size.

    PDFs exceeding the page limit are truncated during parsing rather than
    skipped entirely (see _parse_pdf).

    Args:
        file_size_bytes: Size of the PDF file in bytes

    Returns:
        Tuple of (should_skip: bool, reason: str | None)
    """
    size_mb = file_size_bytes / (1024 * 1024)

    if size_mb > settings.MAX_PDF_SIZE_MB:
        return (
            True,
            f"File size {size_mb:.1f}MB exceeds limit of {settings.MAX_PDF_SIZE_MB}MB",
        )

    return False, None


class ParsedText:
    def __init__(self, doc_id: str, text: str, page_spans: Optional[list[dict]] = None):
        self.doc_id = doc_id
        self.text = text
        self.page_spans = page_spans or []


class ParsingService:
    def __init__(self, export_dir: str):
        self.export_dir = Path(export_dir)
        self.norm_dir = self.export_dir / "data" / "normalized"
        self.norm_dir.mkdir(parents=True, exist_ok=True)

    async def parse_saved_file(
        self, doc_id: str, file_path: str
    ) -> Optional[ParsedText]:
        """
        Parse a saved file (PDF or HTML) with guardrails and async execution.

        Args:
            doc_id: Document identifier
            file_path: Path to the file to parse

        Returns:
            ParsedText object or None if parsing fails or file should be skipped
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("File not found for %s: %s", doc_id, file_path)
            return None

        # Check file size guardrails before parsing
        file_size = path.stat().st_size

        if path.suffix.lower() == ".pdf":
            # Quick check: skip if file is too large
            should_skip, skip_reason = should_skip_large_pdf(file_size)
            if should_skip:
                logger.warning("Skipping PDF %s: %s", doc_id, skip_reason)
                return None

        try:
            # Run parsing in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()

            if path.suffix.lower() == ".pdf":
                timeout = settings.PDF_PARSE_TIMEOUT

                def parse_func():
                    return self._parse_pdf(doc_id, path)
            else:
                timeout = settings.HTML_PARSE_TIMEOUT

                def parse_func():
                    return self._parse_html(doc_id, path)

            # Execute with timeout
            result = await asyncio.wait_for(
                loop.run_in_executor(None, parse_func), timeout=timeout
            )

            return result

        except asyncio.TimeoutError:
            logger.warning("Parsing timeout for %s after %.1fs", doc_id, timeout)
            return None
        except Exception as e:
            logger.warning("Parsing failed for %s: %s", doc_id, e)
            return None

    def _parse_pdf(self, doc_id: str, path: Path) -> ParsedText:
        """
        Parse PDF file and extract text.

        Truncates to MAX_PDF_PAGES if the document exceeds the limit.
        """
        doc = fitz.open(path)

        # Check page count after opening - truncate if too large
        page_count = len(doc)
        pages_to_parse = min(page_count, settings.MAX_PDF_PAGES)
        if page_count > settings.MAX_PDF_PAGES:
            logger.warning(
                "PDF %s has %d pages, truncating to first %d pages",
                doc_id,
                page_count,
                settings.MAX_PDF_PAGES,
            )

        page_spans = []
        texts = []
        char_offset = 0

        try:
            for i in range(pages_to_parse):
                page = doc[i]
                txt = page.get_text("text")
                texts.append(txt)
                start = char_offset
                char_offset += len(txt)
                page_spans.append(
                    {"page": i + 1, "char_start": start, "char_end": char_offset}
                )

            full_text = "\n".join(texts)

            # Check total text length
            if len(full_text) > settings.MAX_TEXT_LENGTH_CHARS:
                logger.warning(
                    "PDF %s text length %d exceeds limit %d, truncating",
                    doc_id,
                    len(full_text),
                    settings.MAX_TEXT_LENGTH_CHARS,
                )
                full_text = full_text[: settings.MAX_TEXT_LENGTH_CHARS]

            return ParsedText(doc_id, full_text, page_spans)
        finally:
            doc.close()

    def _parse_html(self, doc_id: str, path: Path) -> ParsedText:
        file_size = path.stat().st_size
        logger.info(
            "[HTML_PARSE] Starting parse for %s (file_size=%d bytes)",
            doc_id,
            file_size,
        )

        scrapling_text = None
        scrapling_error = None

        # Prefer Scrapling's DOM extraction when available
        if Fetcher is not None:
            try:
                # Some sites embed JSON-escaped strings; get cleaned text via Scrapling's methods
                page = Fetcher.from_file(str(path))
                scrapling_text = page.get_all_text(
                    ignore_tags=("script", "style", "noscript", "meta", "link")
                )
                logger.info(
                    "[HTML_PARSE] Scrapling result for %s: %d chars",
                    doc_id,
                    len(scrapling_text) if scrapling_text else 0,
                )
                if scrapling_text and len(scrapling_text) > 0:
                    page_spans = [
                        {"page": 1, "char_start": 0, "char_end": len(scrapling_text)}
                    ]
                    return ParsedText(doc_id, scrapling_text, page_spans)
            except Exception as e:
                scrapling_error = str(e)
                logger.warning(
                    "[HTML_PARSE] Scrapling failed for %s: %s",
                    doc_id,
                    scrapling_error,
                )
        else:
            logger.info("[HTML_PARSE] Scrapling not available, using BeautifulSoup")

        # Fallback: BeautifulSoup readability approximation
        logger.info("[HTML_PARSE] Using BeautifulSoup fallback for %s", doc_id)
        html = path.read_text(encoding="utf-8", errors="ignore")
        logger.info("[HTML_PARSE] Raw HTML length for %s: %d chars", doc_id, len(html))

        soup = BeautifulSoup(html, "lxml")

        # Try to prioritize main content regions if present
        candidates = []
        matched_selectors = []
        for selector in [
            "article",
            "main",
            "#content",
            "#main",
            ".content",
            ".article",
        ]:
            found = soup.select(selector)
            if found:
                candidates.extend(found)
                matched_selectors.append(f"{selector}({len(found)})")

        if matched_selectors:
            logger.info(
                "[HTML_PARSE] Matched selectors for %s: %s",
                doc_id,
                ", ".join(matched_selectors),
            )
        else:
            logger.info(
                "[HTML_PARSE] No content selectors matched for %s, using fallback elements",
                doc_id,
            )

        nodes = (
            candidates
            if candidates
            else soup.find_all(["article", "section", "div", "p", "h1", "h2", "h3"])
        )

        logger.info("[HTML_PARSE] Found %d nodes for %s", len(nodes), doc_id)

        paragraphs = []
        for el in nodes:
            t = el.get_text(" ", strip=True)
            if t:
                paragraphs.append(t)

        text = "\n".join(paragraphs)
        page_spans = [{"page": 1, "char_start": 0, "char_end": len(text)}]

        logger.info(
            "[HTML_PARSE] Final result for %s: %d chars from %d paragraphs (scrapling=%s, bs_selectors=%s)",
            doc_id,
            len(text),
            len(paragraphs),
            len(scrapling_text)
            if scrapling_text
            else "failed"
            if scrapling_error
            else "n/a",
            ",".join(matched_selectors) if matched_selectors else "fallback",
        )

        return ParsedText(doc_id, text, page_spans)
