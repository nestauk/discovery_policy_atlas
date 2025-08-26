from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def stable_hash(value: Any) -> str:
    """Create a stable sha256 hash for any JSON-serializable value."""
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except Exception:
        data = str(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class DiskCache:
    """Very small utility for deterministic on-disk caching of LLM calls.

    Keys should already be sufficiently unique. Values are stored as JSON files.
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        _ensure_dir(self.base_dir)

    def _key_to_path(self, key: str) -> Path:
        # Nest by first two bytes to avoid too many files per directory
        prefix = key[:2]
        dir_path = self.base_dir / prefix
        _ensure_dir(dir_path)
        return dir_path / f"{key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        path = self._key_to_path(key)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
