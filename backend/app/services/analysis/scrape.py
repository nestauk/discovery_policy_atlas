from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

import httpx
from bs4 import BeautifulSoup

try:
    from scrapling.fetchers import Fetcher  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Fetcher = None


logger = logging.getLogger(__name__)


def _fetch_html_sync(url: str, timeout: float = 30.0) -> Tuple[str, str]:
    """Synchronous HTML fetch with Scrapling if available, otherwise httpx+bs4.

    Returns (html, text). Text is the main content concatenated.
    """

    def _extract_text(html_str: str) -> str:
        soup = BeautifulSoup(html_str, "lxml")
        candidates = []
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
        nodes = (
            candidates
            if candidates
            else soup.find_all(["article", "section", "div", "p", "h1", "h2", "h3"])
        )
        parts = []
        for el in nodes:
            t = el.get_text(" ", strip=True)
            if t:
                parts.append(t)
        return "\n".join(parts)

    def _follow_meta_refresh(base_url: str, html_str: str) -> Optional[str]:
        soup = BeautifulSoup(html_str, "lxml")
        meta = soup.find(
            "meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"}
        )
        if not meta:
            return None
        content = meta.get("content") or meta.get("CONTENT")
        if not content or "url=" not in content.lower():
            return None
        try:
            after = content.split("url=", 1)[1].strip().strip("\"'")
        except Exception:
            return None
        target = httpx.URL(after, base=base_url).human_repr()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Referer": base_url,
        }
        try:
            with httpx.Client(
                timeout=timeout, headers=headers, follow_redirects=True
            ) as client:
                r = client.get(target)
                r.raise_for_status()
                return r.text
        except Exception:
            return None

    if Fetcher is not None:
        page = Fetcher.get(url, stealthy_headers=True, timeout=timeout)
        html = page.html
        base_for_refresh = getattr(page, "url", url)
        redirected = _follow_meta_refresh(base_for_refresh, html)
        if redirected:
            html = redirected
            text = _extract_text(html)
        else:
            text = page.get_all_text(
                ignore_tags=("script", "style", "noscript", "meta", "link")
            )
        return html, text

    # Fallback: httpx sync client
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text
        redirected = _follow_meta_refresh(str(resp.url), html)
        if redirected:
            html = redirected
        text = _extract_text(html)
        return html, text


async def async_fetch_html(url: str, timeout: float = 30.0) -> Tuple[str, str]:
    """Async wrapper around the synchronous HTML fetcher."""
    return await asyncio.to_thread(_fetch_html_sync, url, timeout)
