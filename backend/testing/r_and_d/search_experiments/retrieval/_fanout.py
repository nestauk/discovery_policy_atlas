"""Shared SR/RCT query fanout for the OpenAlex arms (A and B).

Production expands each boolean query into base + systematic-review + RCT variants (references.py:
`base`, `({base}) AND {SYSTEMATIC_REVIEW_CLAUSE}`, `({base}) AND {RCT_CLAUSE}`). Both Arm A
(arms/arm_a.py, single-pass) and Arm B (retrieval/openalex_client.py, inside the loop) reuse this.

The clause strings are passed IN (the caller imports SYSTEMATIC_REVIEW_CLAUSE / RCT_CLAUSE from
`app.services.analysis.references`), so this stays a pure, app-free, offline-testable helper.
"""

from __future__ import annotations


def fanout(
    base: str, enabled: bool, sr_clause: str, rct_clause: str
) -> list[tuple[str, str]]:
    """Expand one boolean into (variant_label, query) pairs — base always; SR/RCT if enabled."""
    variants = [("base", base)]
    if enabled:
        variants.append(("systematic_review", f"({base}) AND {sr_clause}"))
        variants.append(("rct", f"({base}) AND {rct_clause}"))
    return variants
