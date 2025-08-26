import re


_HYPHEN_LINEBREAK_RE = re.compile(r"-\n\s*")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Lightweight normalization preserving structure.

    - De-hyphenate across line breaks: '-\n' → ''
    - Collapse runs of spaces/tabs
    - Collapse 3+ newlines to 2 newlines
    """

    if not text:
        return text

    normalized = _HYPHEN_LINEBREAK_RE.sub("", text)
    normalized = _MULTISPACE_RE.sub(" ", normalized)
    normalized = _MULTINEWLINE_RE.sub("\n\n", normalized)
    return normalized.strip()
