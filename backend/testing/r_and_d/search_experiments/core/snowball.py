"""Citation snowballing — score + promote candidates reached from relevant seeds (spec §4.3 Step 3).

Faithful port of PF `score_snowball_candidate` (`agents/.../snowball/snowball_agent.py:319-365`).
Seeds = papers judged >=2 (Highly/Perfect). From each seed we walk the citation graph one hop:

    backward: the seed's REFERENCES  (older papers it builds on)
    forward : the papers that CITE the seed  (newer work building on it)

Each seed->candidate link is an EDGE. A candidate reached from several seeds has several edges,
and PF SUMS the score over them — so a paper co-cited by many relevant seeds scores higher. That
co-citation signal is the whole point of snowballing, and it is why we score over edges rather
than over a single merged Candidate (a plain `max(seed_relevance)` would discard it).

PF's per-candidate score (ported verbatim, summed over that candidate's edges):

    score = Σ_edges [ seed_relevance_bias · seed_relevance
                      + influential_bias  · is_influential          (forward + Arm C only)
                      + count_bias        · candidate_count ]

with `count_bias` and `candidate_count` direction-specific:
  - forward : count_bias = -0.005   candidate_count = max(reference_count, n_edges)
  - backward: count_bias = -0.0005  candidate_count = max(cited_by_count,  n_edges)

> ★ Faithfulness notes (matching PF exactly, with only context-forced changes):
> 1. The `count_bias · candidate_count` term sits INSIDE PF's per-edge loop, so it is added once
>    per edge -> effectively × n_edges. We replicate that (it is PF's actual behaviour).
> 2. PF penalises FORWARD candidates by their reference count and BACKWARD by their citation
>    count (different DataFrame columns). We model this with `Candidate.reference_count`.
> 3. `influential_bias = 0.1` is forward-only AND Arm-C-only — OpenAlex exposes no influence
>    signal, so `caps.has_influential` gates it off for Arm B (source-forced, spec §4.3 diff #2).
> 4. PF's `num_contexts_bias` and `seed_citation_count_bias` are 0 in its defaults and the spec,
>    so they are dropped — a ×0 term, so this is exact, not a simplification.
> The is_influential flag is captured PER EDGE at fetch time (it is a property of the specific
> citation), so build edges before any dedupe/merge folds candidates together.

REPL usage (no main()/argparse — spec conventions):
    from core.snowball import SnowballEdge, build_edges, score_snowball_candidate, promote_snowball
    edges = build_edges(seed, source_returned_candidates)        # one seed's hop
    promoted = promote_snowball(all_edges, direction="forward", caps=arm_c_caps)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from config import CONFIG
from core.source import Candidate, Capabilities

Direction = Literal["forward", "backward"]


@dataclass
class SnowballEdge:
    """One seed->candidate citation link (a graph edge).

    `seed_relevance` is the seed's judged relevance carried to the candidate — PF's
    `seed_relevance` is the RAW 0-3 level (snowball_agent.py reads `relevance_judgement.relevance`,
    the 0-3 bucket), NOT a [0,1] normalisation. `is_influential` is whether THIS citation is
    influential (S2 forward signal) — captured per edge, since the same candidate reached from
    a different seed may differ.
    """

    candidate: Candidate
    seed_relevance: float
    is_influential: bool = False


def build_edges(seed: Candidate, reached: Iterable[Candidate]) -> list[SnowballEdge]:
    """Make seed->candidate edges from one seed's hop. `seed_relevance = seed.level` (raw 0-3).

    PF carries the seed's RAW 0-3 relevance level (snowball_agent.py:163/250 read
    `relevance_judgement.relevance`) and pairs it with biases (0.1 influence, -0.005/-0.0005
    count) calibrated against that 0-3 scale. Dividing by 3 here would shrink the seed term ~3x
    and inflate those other terms' relative weight, so we carry the raw level (faithfulness fix,
    2026-06-22 — earlier drafts wrongly normalised to [0,1]). Seeds are level >= 2 (PF's
    `relevance > 1`), so seed_relevance is 2.0 or 3.0 in practice.
    Captures each candidate's `is_influential` NOW (before any later merge unions the flag),
    because PF treats influence as a property of the individual citation.
    """
    seed_rel = float(seed.level or 0)
    return [
        SnowballEdge(
            candidate=c, seed_relevance=seed_rel, is_influential=c.is_influential
        )
        for c in reached
    ]


def _candidate_count(cand: Candidate, direction: Direction, n_edges: int) -> int:
    """PF's direction-specific `candidate_citation_count` with its `max(·, n_edges)` floor."""
    if direction == "forward":
        return max(cand.reference_count, n_edges)
    return max(cand.cited_by_count, n_edges)


def score_snowball_candidate(
    edges: list[SnowballEdge], direction: Direction, caps: Capabilities
) -> float:
    """Score ONE candidate from its edges (PF `score_snowball_candidate`, summed over edges)."""
    if not edges:
        return 0.0
    w = CONFIG.snowball
    cand = edges[0].candidate
    count = _candidate_count(cand, direction, len(edges))
    if direction == "forward":
        count_bias = w.forward_citation_count_bias
        # Influence term is forward-only and Arm-C-only (source-forced for Arm B).
        influential_bias = w.influential_bias if caps.has_influential else 0.0
    else:
        count_bias = w.backward_citation_count_bias
        influential_bias = 0.0  # PF: backward carries no influence term

    score = 0.0
    for e in (
        edges
    ):  # PF sums every term per edge (incl. the constant count penalty -> ×n_edges)
        score += (
            w.seed_relevance_bias * e.seed_relevance
            + influential_bias * int(e.is_influential)
            + count_bias * count
        )
    return score


def group_edges_by_candidate(
    edges: Iterable[SnowballEdge],
) -> dict[str, list[SnowballEdge]]:
    """Group edges by candidate paper_id (the co-citation grouping PF scores over)."""
    by_id: dict[str, list[SnowballEdge]] = defaultdict(list)
    for e in edges:
        by_id[e.candidate.paper_id].append(e)
    return dict(by_id)


def promote_snowball(
    edges: Iterable[SnowballEdge],
    direction: Direction,
    caps: Capabilities,
    top_k: int | None = None,
) -> list[Candidate]:
    """Score every candidate over its edges and promote the top-k (PF: top ~200 each direction).

    Stable sort by score desc (PF `sort_values(..., kind="stable")`), so ties keep discovery
    order. Records the computed score on `cand.seed_relevance` for downstream inspection (the
    field is otherwise unused after snowball — ranking reads level/rerank/year/cites, §4.3 Step 5).
    """
    top_k = top_k or CONFIG.budgets.snowball_top_k
    grouped = group_edges_by_candidate(edges)
    scored = [
        (score_snowball_candidate(cand_edges, direction, caps), cand_edges[0].candidate)
        for cand_edges in grouped.values()
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)  # Python sort is stable
    promoted: list[Candidate] = []
    for score, cand in scored[:top_k]:
        cand.seed_relevance = score
        promoted.append(cand)
    return promoted
