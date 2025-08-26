from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


SAFE_CHARS_RE = re.compile(r"[^a-zA-Z0-9._-]+")
UNDERSCORE_RUNS_RE = re.compile(r"_+")


def sanitize_id_to_filename(identifier: str, max_len: int = 128) -> str:
    """Convert a doc identifier (URL/DOI/etc.) into a filesystem-safe basename.

    - Prefer netloc+path for URLs
    - Replace non-safe characters with '_'
    - Collapse runs of underscores
    - Truncate to `max_len`; append 8-char hash to disambiguate if truncated
    """

    raw = identifier or ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        base = f"{parsed.netloc}{parsed.path}"
    else:
        base = raw

    base = base.strip().strip("/")
    base = SAFE_CHARS_RE.sub("_", base)
    base = UNDERSCORE_RUNS_RE.sub("_", base)
    if not base:
        base = "doc"

    if len(base) > max_len:
        digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
        base = f"{base[: max_len - 9]}_{digest}"

    return base
