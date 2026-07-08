"""Shared helpers for the per-leg query formulation modules (dense_s2 / keyword_s2).

The dense and keyword legs formulate SEPARATELY (PF's two-agent split) with their own prompts
and cache namespaces, but the way both render judged-relevant exemplars into the reformulation
'papers' block is identical — that one helper lives here so the two modules don't duplicate it.
"""

from __future__ import annotations

from core.source import Candidate


def exemplar_block(exemplars: list[Candidate], max_chars: int = 300) -> str:
    """Render judged-relevant exemplars to the reformulation 'papers' block (title + snippet)."""
    lines = []
    for e in exemplars:
        body = (e.abstract or "").strip().replace("\n", " ")
        if len(body) > max_chars:
            body = body[: max_chars - 1] + "…"
        lines.append(f"- {e.title or '(untitled)'}" + (f": {body}" if body else ""))
    return "\n".join(lines) if lines else "(none)"
