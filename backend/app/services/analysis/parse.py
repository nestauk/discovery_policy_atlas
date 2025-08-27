from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

try:
    from scrapling.fetchers import Fetcher  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Fetcher = None


logger = logging.getLogger(__name__)


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

    def parse_saved_file(self, doc_id: str, file_path: str) -> Optional[ParsedText]:
        path = Path(file_path)
        if not path.exists():
            return None
        try:
            if path.suffix.lower() == ".pdf":
                return self._parse_pdf(doc_id, path)
            else:
                return self._parse_html(doc_id, path)
        except Exception as e:
            logger.warning("Parsing failed for %s: %s", doc_id, e)
            return None

    def _parse_pdf(self, doc_id: str, path: Path) -> ParsedText:
        doc = fitz.open(path)
        page_spans = []
        texts = []
        char_offset = 0
        for i, page in enumerate(doc):
            txt = page.get_text("text")
            texts.append(txt)
            start = char_offset
            char_offset += len(txt)
            page_spans.append(
                {"page": i + 1, "char_start": start, "char_end": char_offset}
            )
        full_text = "\n".join(texts)
        return ParsedText(doc_id, full_text, page_spans)

    def _parse_html(self, doc_id: str, path: Path) -> ParsedText:
        # Prefer Scrapling’s DOM extraction when available
        if Fetcher is not None:
            try:
                # Some sites embed JSON-escaped strings; get cleaned text via Scrapling's methods
                page = Fetcher.from_file(str(path))
                text = page.get_all_text(
                    ignore_tags=("script", "style", "noscript", "meta", "link")
                )
                if text and len(text) > 0:
                    page_spans = [{"page": 1, "char_start": 0, "char_end": len(text)}]
                    return ParsedText(doc_id, text, page_spans)
            except Exception:
                pass

        # Fallback: BeautifulSoup readability approximation
        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        # Try to prioritize main content regions if present
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

        paragraphs = []
        for el in nodes:
            t = el.get_text(" ", strip=True)
            if t:
                paragraphs.append(t)
        text = "\n".join(paragraphs)
        page_spans = [{"page": 1, "char_start": 0, "char_end": len(text)}]
        return ParsedText(doc_id, text, page_spans)
