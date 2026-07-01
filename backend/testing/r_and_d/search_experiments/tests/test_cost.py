"""Offline tests for reporting.cost — the derived per-arm $ model.

Pins the unit-cost arithmetic, the fixed gpt-5.5 + gpt-4.1 call counts, and the one piece of real
logic: the `actual` view must dedupe judging across arms (judge cache pays each (query,paper) once),
so a paper judged by two arms is counted ONCE, not twice.

Boolean formulation for Arms A/B is priced at gpt-4.1 (settings.BOOLEAN_QUERY_MODEL), NOT gpt-5.5,
and at BOOLEAN_N_RUNS calls per event (the prod generator loops); Arm C formulates via gpt-5.5 S2
legs, so it makes zero gpt-4.1 calls. See cost.py's model-map docstring.
"""

from __future__ import annotations

import pytest

from reporting import cost


def _rec(judged):  # judged: list[(paper_id, level)] -> a persisted-shape arm record
    return {
        "n_judged": sum(lv is not None for _, lv in judged),
        "ranked": [
            {"paper_id": p, "rank": i, "level": lv} for i, (p, lv) in enumerate(judged)
        ],
    }


def test_unit_costs_match_rates():
    # judge: 1000 in @ $0.75/M + 200 out @ $4.50/M
    assert cost.judge_unit_cost(200) == pytest.approx(0.00075 + 0.0009)
    # safe output (600) costs strictly more
    assert cost.judge_unit_cost(600) > cost.judge_unit_cost(200)
    # gpt-5.5: 800 in @ $5/M + 500 out @ $30/M
    assert cost.llm_unit_cost() == pytest.approx(0.004 + 0.015)
    # gpt-4.1 boolean: 700 in @ $2/M + 150 out @ $8/M
    assert cost.boolean_unit_cost() == pytest.approx(0.0014 + 0.0012)


def test_g55_standalone_counts():
    # gpt-5.5 only (booleans are gpt-4.1, counted separately). A = criteria(1); B = suggest(1) +
    # criteria(1) + analysis(2); C = suggest+kw+dense formulation(5) + criteria(1) + analysis(2).
    assert cost.g55_standalone_calls("arm_a") == 1
    assert cost.g55_standalone_calls("arm_b") == 4
    assert cost.g55_standalone_calls("arm_c") == 8


def test_boolean_call_counts():
    # gpt-4.1 events × BOOLEAN_N_RUNS: A formulates once, B formulates + reformulates, C uses gpt-5.5.
    assert cost.boolean_calls("arm_a") == 1 * cost.BOOLEAN_N_RUNS
    assert cost.boolean_calls("arm_b") == 2 * cost.BOOLEAN_N_RUNS
    assert cost.boolean_calls("arm_c") == 0


def test_arm_query_cost_components():
    rec = _rec([("p1", 3), ("p2", 0), ("p3", None)])  # 2 judged (p3 unjudged)
    c = cost.arm_query_cost("arm_a", rec, judge_out=200)
    assert c["n_judged"] == 2
    assert c["judge_usd"] == pytest.approx(2 * cost.judge_unit_cost(200))
    assert c["llm_usd"] == pytest.approx(
        1 * cost.llm_unit_cost()
    )  # A = 1 gpt-5.5 call (criteria only)
    assert c["boolean_usd"] == pytest.approx(
        cost.boolean_calls("arm_a") * cost.boolean_unit_cost()
    )  # A = 5 gpt-4.1 calls (boolean formulation)
    assert c["rerank_usd"] == 0.0  # Arm A has no rerank
    # Arm B incurs a rerank request
    cb = cost.arm_query_cost("arm_b", rec, judge_out=200)
    assert cb["rerank_usd"] == pytest.approx(cost.COHERE_USD_PER_1K_REQUESTS / 1000)


def test_actual_run_dedupes_judging_across_arms():
    # q1: arm_a judged {p1,p2}; arm_b judged {p2,p3}. Union = {p1,p2,p3} = 3 unique, not 4.
    by_arm = {
        "arm_a": {"q1": _rec([("p1", 3), ("p2", 2)])},
        "arm_b": {"q1": _rec([("p2", 1), ("p3", 0)])},
        "arm_c": {},
    }
    act = cost.actual_run_cost(by_arm, judge_out=200)
    assert act["n_attributed_judged"] == 4  # naive sum
    assert act["n_unique_judged"] == 3  # cache-deduped
    assert act["judge_usd"] == pytest.approx(3 * cost.judge_unit_cost(200))


def test_attributed_sum_is_per_arm_total():
    by_arm = {
        "arm_a": {"q1": _rec([("p1", 3)])},
        "arm_b": {"q1": _rec([("p2", 2)])},
        "arm_c": {},
    }
    attr = cost.attributed_costs(by_arm, judge_out=200)
    assert attr["total"]["total_usd"] == pytest.approx(
        attr["arm_a"]["total_usd"]
        + attr["arm_b"]["total_usd"]
        + attr["arm_c"]["total_usd"]
    )
    assert attr["arm_c"]["n_queries"] == 0  # empty arm contributes nothing
