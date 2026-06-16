"""Shared bootstrap for smoke scripts — import this FIRST in every smoke/*.py.

Smoke scripts live in this subdir, so the project root (where config.py / judge.py /
metrics.py live) isn't on sys.path by default. This adds it, then imports config to run
the backend/.env bootstrap (so OPENALEX_* etc. resolve) BEFORE any `app.*` import.

Usage at the top of a smoke script:
    import _bootstrap  # noqa: F401  -- path + env setup, must be first
    from judge import ...

Also exposes `rule(title)`, the shared section-header printer for smoke output.
"""

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402, F401  -- triggers the backend/.env bootstrap


def rule(title: str) -> None:
    """Print a section-header rule (shared by the smoke scripts)."""
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)
