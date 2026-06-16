"""Phase 1 smoke test — metrics (pure, offline, no API).

Shows what the parity-tested metric functions produce on worked examples, so the
inflation/recall/nDCG behaviour is visible rather than just asserted. Run:

    uv run smoke/phase1_metrics.py
"""

import _bootstrap  # noqa: F401  -- path + env setup, must be first
from _bootstrap import rule

from metrics import (
    find_dcg,
    inflation_factor,
    k_est,
    lower_bound_corrected_ndcg,
    precision_at_k,
    recall_at_k_est,
)


def run_smoke():
    rule("1. inflation_factor / k_est  (pooled-normalizer denominator, §4.6)")
    print("   perfect_count  factor   k_est")
    for n in (1, 2, 3, 5, 10, 100):
        print(f"   {n:>12}   {inflation_factor(n):5.3f}   {k_est(n):>5}")
    print(
        "   note: only count=2 clears the x2 floor (x2.885); the x10 cap bites only at count=1"
    )

    rule("2. recall_at_k_est  (Perfect-in-top-k_est / k_est)")
    ranked = ["a", "x", "b", "c"]  # 'x' is unjudged -> dropped before the window
    judgements = {"a": 3, "b": 3, "c": 0}
    pool_perfect = 1  # -> k_est = 10
    r = recall_at_k_est(ranked, judgements, pool_perfect)
    print(f"   ranked={ranked}  judged={judgements}  pool_perfect={pool_perfect}")
    print(f"   k_est=10, Perfect in window={{a,b}}=2  ->  recall = 2/10 = {r}")
    print(
        "   (denominator is k_est, NOT raw perfect count -> recall is capped at 1/factor)"
    )

    rule("3. precision_at_k")
    print(
        f"   precision@2 over [a,b,c,d] judged -> {precision_at_k(['a','b','c','d'], {'a':3,'b':0,'c':3,'d':3}, k=2)}"
    )

    rule("4. find_dcg (NATURAL log) + lower_bound_corrected_ndcg")
    rels = [3, 0, 2, 1]
    print(f"   relevances={rels}")
    print(f"   find_dcg = {find_dcg(rels):.4f}  (natural-log discount, not log2)")
    print(
        f"   corrected nDCG = {lower_bound_corrected_ndcg(rels):.4f}  (1.0 if sorted desc, 0.0 if asc/all-equal)"
    )


run_smoke()
