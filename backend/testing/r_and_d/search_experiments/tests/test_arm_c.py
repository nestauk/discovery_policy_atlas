"""Offline tests for Arm C (Phase 8).

Arm C is Arm B with `source = S2Source()`; the Arm-C loop behaviour (dense leg + influential
snowball + snippet blend firing under all-True caps) is already covered by test_broad_search
(ARM_C = Capabilities(has_dense=True, …)) and the S2 mappers/throttle by test_s2_client. So here we
just pin the two Arm-C-specific facts: it reuses Arm B's source-agnostic loop helpers (not a fork),
and its result dataclass has the Phase-9 schema."""

from __future__ import annotations

from arms import arm_b, arm_c
from arms.arm_c import ArmCResult


def test_arm_c_reuses_arm_b_loop_helpers():
    # Intentional reuse — the judge_fn + ranked-record shaping are source-agnostic, not duplicated.
    assert arm_c._make_judge_fn is arm_b._make_judge_fn
    assert arm_c._ranked_records is arm_b._ranked_records


def test_arm_c_result_shape():
    r = ArmCResult(query_id="q1", query_text="x", n_pool=10, n_judged=5)
    assert (r.query_id, r.n_pool, r.n_judged, r.ranked) == ("q1", 10, 5, [])
