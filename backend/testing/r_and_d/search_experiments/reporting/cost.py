"""Per-arm $ cost reconstruction — the dollar twin of `_timing` / `plots.standalone_latency`.

Cost here is DERIVED, not measured. Wall-time has to be timed live (`StageTimer`), but a dollar
figure is `calls × tokens × price`, and the dominant term — per-paper judging — is reconstructed
from the persisted `n_judged` (results/arms/{arm}/{qid}.json). So this module needs NO live
instrumentation and NO re-run: it prices any completed run straight off the on-disk results. Change
your rates → re-run the report, not the experiment (which is why cost is NOT persisted into the
result JSON — that would duplicate derivable data and go stale the moment a price changes).

Model map (see README): gpt-5.4-mini = per-paper judging (the volume); gpt-4.1 = Arm A/B boolean
(re)formulation (the production ReferencesService generator, BOOLEAN_N_RUNS calls per event);
gpt-5.5 = criteria + query analysis + parametric suggest + Arm C's S2 keyword/dense (re)formulation
(the leverage); Cohere = rerank.

Two views, mirroring the cold/warm latency split:
  attributed — each arm priced as if standalone (Σ its own n_judged + its own gpt-5.5 calls).
               Use this to COMPARE arms. Double-counts judging that the real run shares.
  actual     — the judge cache pays each (query, paper) ONCE (union across arms), and criteria
               (1/query) + query-analysis (2/query, B&C) are extracted once. This is the real bill.

THREE assumptions are surfaced as editable constants — only the first is exact:
  PRICES   — $/1M tokens per model. Your real OpenAI/Cohere rates; swap freely. (EXACT once set.)
  TOKENS   — estimated tokens/call. JUDGE_OUT is the soft spot: gpt-5.4-mini's minimal-reasoning is
             NOT wired (judge.py:353), so true output may exceed JUDGE_OUT_TOKENS — hence the
             base/safe pair, which drives the headline range. Measure judge output to collapse it.
  G55_* / G41_*  — per-arm gpt-5.5 and gpt-4.1 call counts, from the fixed pipeline structure (not
             data-derived). G41 formulation EVENTS are multiplied by BOOLEAN_N_RUNS (the prod
             boolean generator loops N times per event — each run is a separate API call).

Caveat: rates are billed at standard input — OpenAI prompt-caching on the stable judge prefix
(criteria+schema) would bill that portion at PRICES[...]['cached_in'] (10× cheaper); not modelled.
NB: Arms A/B formulate booleans through the production ReferencesService generator
(references.py:228 via openalex_client.py:220), wired to settings.BOOLEAN_QUERY_MODEL = gpt-4.1
(NOT gpt-5.5), and it loops settings.BOOLEAN_QUERY_N_RUNS times per event, so each formulation is
N separate calls. Arm C's keyword/dense legs are the experiment's own gpt-5.5 S2 formulators
(dense_s2.py / keyword_s2.py — one structured call each), so Arm C makes ZERO gpt-4.1 calls.

REPL usage (no main()/argparse — spec conventions):
    from reporting.cost import run_cost_report, attributed_costs, actual_run_cost
    report = run_cost_report()                       # loads results/arms, prints + returns the breakdown
    attributed_costs(load_all_arms())                # per-arm standalone $ (base + safe)
    actual_run_cost(load_all_arms(), judge_out=600)  # the real bill at a chosen judge-output size
"""

from __future__ import annotations

from _backend import get_settings
from config import CONFIG
from reporting.collect_results import ARMS, load_all_arms

# --------------------------------------------------------------------------- #
# Rates ($/1M tokens) — your real OpenAI + Cohere prices. `cached_in` is recorded for reference
# (prompt-caching discount) but not applied; standard `in` is used (the conservative bill).
# --------------------------------------------------------------------------- #
PRICES: dict[str, dict[str, float]] = {
    "gpt-5.4-mini": {"in": 0.75, "out": 4.50, "cached_in": 0.075},  # judging
    "gpt-5.5": {
        "in": 5.00,
        "out": 30.00,
        "cached_in": 0.50,
    },  # criteria / query analysis / suggest / Arm C S2 formulation
    "gpt-4.1": {
        "in": 2.00,
        "out": 8.00,
        "cached_in": 0.50,
    },  # Arm A/B boolean (re)formulation (production BOOLEAN_QUERY_MODEL)
}
COHERE_USD_PER_1K_REQUESTS = 2.00  # placeholder; Arm B/C rerank ≈ 1 request/query

_SETTINGS = (
    get_settings()
)  # production Settings — source of the boolean formulation model + runs
JUDGE_MODEL = CONFIG.models.judge_model  # gpt-5.4-mini
LLM_MODEL = (
    CONFIG.models.formulation_model
)  # gpt-5.5 (criteria/intent/suggest/Arm C S2 formulation share this tier)
BOOLEAN_MODEL = (
    _SETTINGS.BOOLEAN_QUERY_MODEL
)  # gpt-4.1 — Arm A/B boolean (re)formulation
BOOLEAN_N_RUNS = (
    _SETTINGS.BOOLEAN_QUERY_N_RUNS
)  # 5 — prod generator loops N calls per event

# --------------------------------------------------------------------------- #
# Tokens per call (ESTIMATES — the price axis is exact, this axis is not).
# --------------------------------------------------------------------------- #
JUDGE_IN_TOKENS = 1000  # criteria block + paper title/abstract + per-criterion schema
JUDGE_OUT_TOKENS = 200  # base: structured per-criterion codes, minimal output
JUDGE_OUT_TOKENS_SAFE = (
    600  # safe: if minimal-reasoning emits reasoning tokens (judge.py:353)
)
LLM_IN_TOKENS = 800
LLM_OUT_TOKENS = 500
BOOL_IN_TOKENS = (
    700
)  # boolean system prompt + short question (re-sent on each of the N runs)
BOOL_OUT_TOKENS = (
    150
)  # one boolean query string (max_tokens=1000, but real output is short)

# --------------------------------------------------------------------------- #
# Per-query call structure by MODEL (fixed pipeline, not data-derived) — see the model map above.
#
# gpt-4.1 (production boolean generator): counted as formulation EVENTS; each event is
# BOOLEAN_N_RUNS separate API calls (references.py loops `for i in range(n_runs)`). Arm C
# formulates via the gpt-5.5 S2 legs, so it makes zero gpt-4.1 calls.
G41_FORMULATION_EVENTS = {
    "arm_a": 1,  # single-pass boolean formulate
    "arm_b": 2,  # keyword formulate (iter 0) + reformulate (iter 1)
    "arm_c": 0,  # S2 keyword/dense legs are gpt-5.5, not the prod boolean generator
}
# gpt-5.5 UNIQUE = per-arm calls NOT shared via cache (one structured call each); criteria (all arms)
# + analysis (B&C) are shared and added once in the `actual` view. STANDALONE = UNIQUE + criteria(1)
# + analysis(2 for B&C) — the per-arm gpt-5.5 cost in isolation.
G55_UNIQUE = {
    "arm_a": 0,  # Arm A's only formulation is the gpt-4.1 boolean; no gpt-5.5-unique call
    "arm_b": 1,  # parametric suggest
    "arm_c": 5,  # suggest + kw formulate/reformulate + dense formulate/reformulate (all S2/gpt-5.5)
}
_ANALYSIS_ARMS = {
    "arm_b",
    "arm_c",
}  # analyse_query (content+intent = 2 calls), shared B↔C
COHERE_ARMS = {"arm_b", "arm_c"}


def g55_standalone_calls(arm: str) -> int:
    """gpt-5.5 calls an arm makes alone: its unique (suggest / Arm C formulation) + criteria(1) + analysis(2 B/C)."""
    return G55_UNIQUE[arm] + 1 + (2 if arm in _ANALYSIS_ARMS else 0)


def boolean_calls(arm: str) -> int:
    """gpt-4.1 boolean-formulation calls an arm makes: EVENTS × BOOLEAN_N_RUNS (the prod generator loops)."""
    return G41_FORMULATION_EVENTS[arm] * BOOLEAN_N_RUNS


# --------------------------------------------------------------------------- #
# Unit costs
# --------------------------------------------------------------------------- #
def _price(model: str) -> dict[str, float]:
    if model not in PRICES:
        raise KeyError(
            f"no price for model {model!r}; add it to reporting.cost.PRICES (have {list(PRICES)})"
        )
    return PRICES[model]


def _call_usd(tok_in: int, tok_out: int, price: dict[str, float]) -> float:
    return tok_in / 1e6 * price["in"] + tok_out / 1e6 * price["out"]


def judge_unit_cost(judge_out: int = JUDGE_OUT_TOKENS) -> float:
    """$ for one per-paper judge call (gpt-5.4-mini) at the given output-token assumption."""
    return _call_usd(JUDGE_IN_TOKENS, judge_out, _price(JUDGE_MODEL))


def llm_unit_cost() -> float:
    """$ for one gpt-5.5 call (criteria / analysis / suggest / Arm C S2 formulation)."""
    return _call_usd(LLM_IN_TOKENS, LLM_OUT_TOKENS, _price(LLM_MODEL))


def boolean_unit_cost() -> float:
    """$ for one gpt-4.1 boolean-formulation call (Arm A/B production generator)."""
    return _call_usd(BOOL_IN_TOKENS, BOOL_OUT_TOKENS, _price(BOOLEAN_MODEL))


# --------------------------------------------------------------------------- #
# Per arm-query + attributed (standalone) aggregation
# --------------------------------------------------------------------------- #
def _judged_ids(rec: dict) -> set[str]:
    """Paper ids this arm actually judged (level set) — the unit the judge cache keys on."""
    return {r["paper_id"] for r in rec.get("ranked", []) if r.get("level") is not None}


def arm_query_cost(arm: str, rec: dict, *, judge_out: int = JUDGE_OUT_TOKENS) -> dict:
    """$ breakdown for one arm-query, priced standalone. `rec` is a persisted result dict."""
    n = rec.get("n_judged", 0)
    judge = n * judge_unit_cost(judge_out)
    boolean = boolean_calls(arm) * boolean_unit_cost()  # gpt-4.1 (Arms A/B; 0 for C)
    llm = g55_standalone_calls(arm) * llm_unit_cost()  # gpt-5.5
    rerank = COHERE_USD_PER_1K_REQUESTS / 1000 if arm in COHERE_ARMS else 0.0
    return {
        "n_judged": n,
        "judge_usd": judge,
        "boolean_usd": boolean,
        "llm_usd": llm,
        "rerank_usd": rerank,
        "total_usd": judge + boolean + llm + rerank,
    }


def attributed_costs(by_arm: dict, *, judge_out: int = JUDGE_OUT_TOKENS) -> dict:
    """Per-arm standalone totals + grand sum. `by_arm[arm][qid] = record` (from load_all_arms)."""
    out: dict[str, dict] = {}
    for arm in ARMS:
        recs = by_arm.get(arm, {})
        rows = [arm_query_cost(arm, r, judge_out=judge_out) for r in recs.values()]
        out[arm] = {
            "n_queries": len(rows),
            "n_judged": sum(r["n_judged"] for r in rows),
            "boolean_usd": sum(r["boolean_usd"] for r in rows),
            "judge_usd": sum(r["judge_usd"] for r in rows),
            "llm_usd": sum(r["llm_usd"] for r in rows),
            "rerank_usd": sum(r["rerank_usd"] for r in rows),
            "total_usd": sum(r["total_usd"] for r in rows),
        }
    out["total"] = {
        k: sum(out[a][k] for a in ARMS)
        for k in (
            "n_queries",
            "n_judged",
            "boolean_usd",
            "judge_usd",
            "llm_usd",
            "rerank_usd",
            "total_usd",
        )
    }
    return out


# --------------------------------------------------------------------------- #
# Actual run cost — judge cache pays each (query, paper) once; criteria/analysis shared
# --------------------------------------------------------------------------- #
def actual_run_cost(by_arm: dict, *, judge_out: int = JUDGE_OUT_TOKENS) -> dict:
    """The real bill for the A→B→C run: union judging + shared criteria/analysis + per-arm formulation."""
    all_qids = set().union(*[set(by_arm.get(a, {})) for a in ARMS]) if by_arm else set()
    unique_judged = 0
    for q in all_qids:
        union = set().union(*[_judged_ids(by_arm.get(a, {}).get(q, {})) for a in ARMS])
        unique_judged += len(union)

    # gpt-5.5: criteria once/query (any arm judged it) + analysis 2/query (if B or C ran)
    # + each arm's UNIQUE formulation calls.
    qids_any = {q for a in ARMS for q in by_arm.get(a, {})}
    qids_bc = {q for a in _ANALYSIS_ARMS for q in by_arm.get(a, {})}
    g55_calls = (
        len(qids_any) * 1
        + len(qids_bc) * 2
        + sum(len(by_arm.get(a, {})) * G55_UNIQUE[a] for a in ARMS)
    )
    # gpt-4.1 booleans are per-arm (each arm formulates its own; not cache-shared across arms).
    boolean_call_total = sum(len(by_arm.get(a, {})) * boolean_calls(a) for a in ARMS)
    rerank_reqs = sum(len(by_arm.get(a, {})) for a in COHERE_ARMS)

    judge = unique_judged * judge_unit_cost(judge_out)
    boolean = boolean_call_total * boolean_unit_cost()
    llm = g55_calls * llm_unit_cost()
    rerank = rerank_reqs * COHERE_USD_PER_1K_REQUESTS / 1000
    return {
        "n_unique_judged": unique_judged,
        "n_attributed_judged": sum(
            r.get("n_judged", 0) for a in ARMS for r in by_arm.get(a, {}).values()
        ),
        "g55_calls": g55_calls,
        "boolean_calls": boolean_call_total,
        "judge_usd": judge,
        "boolean_usd": boolean,
        "llm_usd": llm,
        "rerank_usd": rerank,
        "total_usd": judge + boolean + llm + rerank,
    }


# --------------------------------------------------------------------------- #
# Report (REPL entry)
# --------------------------------------------------------------------------- #
def run_cost_report(
    by_arm: dict | None = None,
    *,
    judge_out_base: int = JUDGE_OUT_TOKENS,
    judge_out_safe: int = JUDGE_OUT_TOKENS_SAFE,
) -> dict:
    """Print + return the cost breakdown (attributed per-arm + actual run), at base & safe judge-output."""
    by_arm = by_arm if by_arm is not None else load_all_arms()
    attr_b = attributed_costs(by_arm, judge_out=judge_out_base)
    attr_s = attributed_costs(by_arm, judge_out=judge_out_safe)
    act_b = actual_run_cost(by_arm, judge_out=judge_out_base)
    act_s = actual_run_cost(by_arm, judge_out=judge_out_safe)

    print(
        f"Rates: {JUDGE_MODEL} ${_price(JUDGE_MODEL)['in']}/{_price(JUDGE_MODEL)['out']} per 1M (in/out); "
        f"{LLM_MODEL} ${_price(LLM_MODEL)['in']}/{_price(LLM_MODEL)['out']}; "
        f"{BOOLEAN_MODEL} ${_price(BOOLEAN_MODEL)['in']}/{_price(BOOLEAN_MODEL)['out']} "
        f"(×{BOOLEAN_N_RUNS} calls/formulation).  "
        f"Judge out tokens: base {judge_out_base} / safe {judge_out_safe}."
    )
    print("\n=== ATTRIBUTED (each arm priced standalone) ===")
    for arm in ARMS:
        a, s = attr_b[arm], attr_s[arm]
        nq = max(a["n_queries"], 1)
        print(
            f"  {arm}: {a['n_queries']:>2}q  {a['n_judged']:>5} judged | "
            f"judge ${a['judge_usd']:6.2f}/${s['judge_usd']:6.2f}  "
            f"bool ${a['boolean_usd']:4.2f}  llm ${a['llm_usd']:5.2f}  rerank ${a['rerank_usd']:4.2f}  "
            f"= ${a['total_usd']:6.2f} / ${s['total_usd']:6.2f}  "
            f"(${a['total_usd'] / nq:.3f}/q base, ${s['total_usd'] / nq:.3f}/q safe)"
        )
    print(
        f"  SUM: ${attr_b['total']['total_usd']:.2f} (base) / ${attr_s['total']['total_usd']:.2f} (safe)"
    )
    print("\n=== ACTUAL RUN (judge cache: each (query,paper) paid once) ===")
    print(
        f"  unique judged {act_b['n_unique_judged']} of {act_b['n_attributed_judged']} attributed "
        f"({1 - act_b['n_unique_judged'] / max(act_b['n_attributed_judged'], 1):.0%} saved by cache); "
        f"{act_b['g55_calls']} gpt-5.5 + {act_b['boolean_calls']} gpt-4.1 calls"
    )
    print(
        f"  judge ${act_b['judge_usd']:.2f}/${act_s['judge_usd']:.2f}  "
        f"boolean ${act_b['boolean_usd']:.2f}  llm ${act_b['llm_usd']:.2f}  rerank ${act_b['rerank_usd']:.2f}"
    )
    print(
        f"  ➡  TOTAL: ${act_b['total_usd']:.2f} (base) / ${act_s['total_usd']:.2f} (safe)"
    )
    return {
        "attributed_base": attr_b,
        "attributed_safe": attr_s,
        "actual_base": act_b,
        "actual_safe": act_s,
    }
