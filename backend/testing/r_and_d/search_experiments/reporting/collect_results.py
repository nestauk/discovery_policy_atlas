"""Phase 9 — three-way metrics over the pooled normalizer (spec §4.6/§4.7).

Reads each arm's persisted per-query results (results/arms/{arm}/{qid}.json, schema
{query_id, ranked: [{paper_id, rank, level}], …}), builds the **pooled normalizer** per query
(the cross-arm ground truth), and computes the headline metric per arm — **`recall@k_est`, read
alongside the raw Perfect-papers-found count** (§4.7's interpretive companion).

The headline is the OVERALL per-arm table. Stratification (use_case × literature_density) is
**secondary** — computed into summary.json, not the headline. And note `literature_density` is a
*soft Phase-5 judgment* (dense/medium/sparse prior on how much relevant literature exists), not a
measured quantity; the rigorous version of "is this a sparse topic?" is just `pool_perfect` (a small
pool → big inflation → a structurally low recall ceiling). So we lead with `pool_perfect`/`k_est`,
and treat the density cut as a coarse reading aid.

Pooled normalizer (§4.6): the relevant-paper denominator is estimated from the UNION of judged
papers across sources. `pooled_judgements` here unions A∪B∪C (each paper is judged once via the
shared judge cache, so levels are consistent — we take the max non-null level seen). `pool_perfect`
= distinct papers judged Perfect(3) in that pool; `k_est = ceil(pool_perfect × factor)`. Because
recall is `Perfect-in-top-k_est ÷ k_est`, it is capped at 1/factor by construction (a "low" recall
is "found X% of an inflated estimate", not "missed half") — the report says so in plain English.

`extra_pools` is a hook for the §4.6 **padding runs** (high-volume sweep, hot-temp suggestions,
depth-2 snowball, S2 lenient dense sweep): drop their results in the same schema under
results/normalizer/ and pass them here to strengthen the denominator. Not built yet (expensive).

NOT YET (deferred, flagged in the Phase-9 scope):
  - the §4.7 reranker sweep — needs per-candidate features (rerank_score/num_snippets/year/cites)
    that the arms don't persist yet; a small schema add before the live runs unlocks it.
  - the §4.6 padding runs themselves.

REPL usage (no main()/argparse — spec conventions):
    from collect_results import run_collect, load_all_arms, pooled_judgements
    summary = run_collect()          # prints the table + returns the aggregate dict
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import mean

from reporting.metrics import (
    HIGHLY,
    adjusted_f1,
    count_relevant,
    k_est,
    lower_bound_corrected_ndcg,
    precision_at_k,
    recall_at_k_est,
)
from queries.loader import load_queries

logger = logging.getLogger(__name__)

ARMS = ("arm_a", "arm_b", "arm_c")
PRECISION_KS = (25, 50, 100, 250)
# `.parents[1]` (not `.parent`) because this module lives in reporting/ — the results/ root is one
# level up, at the package root. Reads the arm outputs written by the runners at search_experiments/results/arms.
_RESULTS_DIR = Path(__file__).resolve().parents[1] / "results" / "arms"


# --------------------------------------------------------------------------- #
# Load + pool (pure given the on-disk results)
# --------------------------------------------------------------------------- #
def load_all_arms(results_dir: Path = _RESULTS_DIR) -> dict[str, dict[str, dict]]:
    """{arm: {query_id: result_record}} for whichever arms have persisted results."""
    out: dict[str, dict[str, dict]] = {}
    for arm in ARMS:
        arm_dir = results_dir / arm
        recs = {}
        if arm_dir.exists():
            for f in sorted(arm_dir.glob("*.json")):
                rec = json.loads(f.read_text())
                recs[rec["query_id"]] = rec
        out[arm] = recs
    return out


def pooled_judgements(
    query_id: str, by_arm: dict[str, dict[str, dict]], extra_pools=()
) -> dict[str, int]:
    """Cross-arm ground truth for one query: paper_id → max non-null level seen across all arms
    (+ any §4.6 padding pools). Each paper is judged once (shared cache) so levels agree; max is
    just a safe merge."""
    pooled: dict[str, int] = {}
    sources = [by_arm.get(arm, {}).get(query_id) for arm in ARMS]
    sources += [pool.get(query_id) for pool in extra_pools]
    for rec in sources:
        if not rec:
            continue
        for r in rec["ranked"]:
            lvl = r.get("level")
            if lvl is not None:
                pooled[r["paper_id"]] = max(pooled.get(r["paper_id"], 0), lvl)
    return pooled


# --------------------------------------------------------------------------- #
# Per-arm-per-query metrics (against the pooled normalizer)
# --------------------------------------------------------------------------- #
def arm_query_metrics(
    arm_rec: dict, pooled: dict[str, int], pool_perfect: int, pool_highly: int
) -> dict:
    """All §4.7 per-query metrics for one arm's ranked list, scored against the pooled judgements.

    Reports the frozen Perfect-cutoff metrics (level==3) AND a PARALLEL "Highly Relevant and above"
    set (level>=2, `_highly` suffix) — same ranked list, relaxed relevance bar. The two never
    interact: each recall uses the pool count + k_est at its OWN threshold (`pool_perfect` vs
    `pool_highly`), so neither can leak into the other.
    """
    ranked_ids = [r["paper_id"] for r in arm_rec["ranked"]]
    rel_in_order = [
        pooled[pid] for pid in ranked_ids if pid in pooled
    ]  # judged levels, rank order

    recall = (
        recall_at_k_est(ranked_ids, pooled, pool_perfect) if pool_perfect > 0 else 0.0
    )
    recall_highly = (
        recall_at_k_est(ranked_ids, pooled, pool_highly, threshold=HIGHLY)
        if pool_highly > 0
        else 0.0
    )
    ndcg = lower_bound_corrected_ndcg(rel_in_order)
    perfect_found = count_relevant(
        pooled, restrict_to=ranked_ids
    )  # pool-Perfects this arm retrieved (rank-independent)
    highly_found = count_relevant(
        pooled, restrict_to=ranked_ids, threshold=HIGHLY
    )  # pool level>=2 (Highly+Perfect) this arm retrieved

    # Retrieval/budget context (2026-06-27): raw perfect_found isn't comparable across arms because
    # they judge DIFFERENT numbers of papers — Arm A judges a full quota (250) off a huge retrieved
    # set, while B/C short-circuit lower once enough Perfects are found. So we report the budget
    # (n_retrieved pre-judge, n_judged) and a budget-normalised YIELD = Perfects surfaced ÷ judgements
    # spent. n_retrieved is keyed `n_retrieved` (Arm A) or `n_pool` (Arm B/C).
    n_judged = arm_rec.get("n_judged") or 0
    n_retrieved = arm_rec.get("n_retrieved") or arm_rec.get("n_pool") or len(ranked_ids)
    return {
        "recall_at_k_est": recall,
        "recall_at_k_est_highly": recall_highly,
        "perfect_found": perfect_found,
        "highly_found": highly_found,
        "ndcg": ndcg,
        "adjusted_f1": adjusted_f1(recall, ndcg),
        "n_retrieved": n_retrieved,
        "n_judged": n_judged,
        "yield_perfect_per_judged": (perfect_found / n_judged) if n_judged else 0.0,
        "yield_highly_per_judged": (highly_found / n_judged) if n_judged else 0.0,
        **{
            f"precision_at_{k}": precision_at_k(ranked_ids, pooled, k)
            for k in PRECISION_KS
        },
    }


# --------------------------------------------------------------------------- #
# Aggregation + report
# --------------------------------------------------------------------------- #
def _mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def collect(by_arm: dict[str, dict[str, dict]], extra_pools=()) -> dict:
    """Per-query metrics for every arm + means, overall and stratified by use_case / density."""
    queries = {q.query_id: q for q in load_queries()}
    per_query: dict[
        str, dict
    ] = {}  # {query_id: {pool_perfect, k_est, arms: {arm: metrics}}}

    for qid in queries:
        pooled = pooled_judgements(qid, by_arm, extra_pools)
        pool_perfect = count_relevant(pooled)
        pool_highly = count_relevant(pooled, threshold=HIGHLY)  # level>=2 pooled count
        entry = {
            "pool_perfect": pool_perfect,
            "k_est": k_est(pool_perfect) if pool_perfect else 0,
            "pool_highly": pool_highly,
            "k_est_highly": k_est(pool_highly) if pool_highly else 0,
            "arms": {},
        }
        for arm in ARMS:
            rec = by_arm.get(arm, {}).get(qid)
            if rec:
                entry["arms"][arm] = arm_query_metrics(
                    rec, pooled, pool_perfect, pool_highly
                )
        per_query[qid] = entry

    def agg(metric: str, arm: str, qids: list[str]) -> float:
        return _mean(
            [
                per_query[q]["arms"][arm][metric]
                for q in qids
                if arm in per_query[q]["arms"]
            ]
        )

    metric_names = [
        "recall_at_k_est",
        "recall_at_k_est_highly",
        "ndcg",
        "adjusted_f1",
        "perfect_found",
        "highly_found",
        "n_retrieved",
        "n_judged",
        "yield_perfect_per_judged",
        "yield_highly_per_judged",
    ] + [f"precision_at_{k}" for k in PRECISION_KS]

    def block(qids: list[str]) -> dict:
        return {arm: {m: agg(m, arm, qids) for m in metric_names} for arm in ARMS}

    all_qids = list(queries)
    strata = {"overall": block(all_qids)}
    for axis, key in (
        ("use_case", lambda q: queries[q].use_case),
        ("density", lambda q: queries[q].literature_density),
    ):
        groups: dict[str, list[str]] = {}
        for qid in all_qids:
            groups.setdefault(str(key(qid)), []).append(qid)
        strata[axis] = {g: block(gq) for g, gq in groups.items()}

    return {"per_query": per_query, "aggregate": strata}


def _print_overall(strata: dict) -> None:
    overall = strata["overall"]
    cols = [
        "recall_at_k_est",
        "ndcg",
        "adjusted_f1",
        "perfect_found",
        "precision_at_25",
    ]
    print(
        f"\n{'arm':<8}"
        + "".join(
            f"{c.replace('_at_k_est', '@k').replace('precision_at_25', 'P@25').replace('adjusted_f1', 'F1'):>14}"
            for c in cols
        )
    )
    for arm in ARMS:
        row = overall[arm]
        print(f"{arm:<8}" + "".join(f"{row[c]:>14.3f}" for c in cols))


def _print_context(strata: dict) -> None:
    """Budget + yield context — read perfect_found against how many papers each arm actually judged.

    Arm A judges a full quota off a huge retrieved set; B/C short-circuit lower — so perfect_found is
    NOT comparable raw. `yield` (Perfects ÷ judgements) normalises for that; retrieved/judged show the
    budgets side by side. See the 2026-06-27 budget-confound note.
    """
    overall = strata["overall"]
    cols = ["n_retrieved", "n_judged", "perfect_found", "yield_perfect_per_judged"]
    labels = {
        "n_retrieved": "retrieved",
        "n_judged": "judged",
        "perfect_found": "perfects",
        "yield_perfect_per_judged": "yield/judged",
    }
    print(
        "\n=== RETRIEVAL CONTEXT (mean over queries): judge budget + Perfect yield, per arm ==="
    )
    print(f"{'arm':<8}" + "".join(f"{labels[c]:>14}" for c in cols))
    for arm in ARMS:
        row = overall[arm]
        print(
            f"{arm:<8}"
            + "".join(
                f"{row[c]:>14.3f}"
                if c == "yield_perfect_per_judged"
                else f"{row[c]:>14.1f}"
                for c in cols
            )
        )
    print(
        "(retrieved/judged = mean candidate count pre-judge / judged; yield = perfects ÷ judged — "
        "budget-normalised, so it's comparable across arms where raw perfects is not.)"
    )


def run_collect(write: bool = True) -> dict:
    """Load arm results, compute metrics, print the headline table, optionally write summary.json."""
    by_arm = load_all_arms()
    counts = {arm: len(recs) for arm, recs in by_arm.items()}
    print(f"Loaded per-arm result counts: {counts}")
    if not any(counts.values()):
        print("No arm results found (run arms' run_all() first). Nothing to collect.")
        return {}

    summary = collect(by_arm)
    pq = summary["per_query"]
    judged_qs = [q for q in pq if pq[q]["pool_perfect"] > 0]
    mean_pp = _mean([pq[q]["pool_perfect"] for q in judged_qs])
    mean_k = _mean([pq[q]["k_est"] for q in judged_qs])
    print(
        f"\nPooled normalizer: {len(judged_qs)}/{len(pq)} queries with ≥1 Perfect; "
        f"mean pool_perfect={mean_pp:.1f}, mean k_est={mean_k:.1f} "
        f"(recall is Perfect-in-top-k_est ÷ k_est — capped at 1/factor, so read it with perfect_found)"
    )
    print(
        "\n=== HEADLINE (mean over queries): recall@k_est + raw Perfect-found, per arm ==="
    )
    _print_overall(summary["aggregate"])
    _print_context(summary["aggregate"])
    print("(use_case × density breakdowns are in summary.json — secondary.)")

    if write:
        out = _RESULTS_DIR.parent / "collect" / "summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nwrote {out}")
    return summary


# `uv run python -m reporting.collect_results` — aggregate persisted arm results, print headline.
if __name__ == "__main__":
    run_collect()
