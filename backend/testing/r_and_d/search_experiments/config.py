"""Frozen experiment configuration (spec §2, §4.3, §4.5, §4.6).

One dataclass, no config system (KISS). Every value here is *frozen for the
experiment's duration* — the whole point of the A→B→C ladder is that arms differ
only in the axis under test, so every shared knob lives in one auditable place.

REPL usage:
    from config import CONFIG
    CONFIG.adaptive.initial_batch_size  # 20

Models are the spec's tiering (§2 "Models" row):
  - gpt-5.4-mini, minimal reasoning -> high-volume per-paper judging + keyword rewrite
  - gpt-5.5                          -> low-volume, high-leverage criteria/intent/reformulation
  - cohere rerank-english-v3.0       -> Arm B & C content blend + §4.7 sweep
These names mirror the gpt-5.x convention already used in
backend/testing/r_and_d/evidence_categorisation/ (default model "gpt-5.2").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Env bootstrap (must run before any `app.core.config` import).
# The backend's pydantic Settings reads `env_file=".env"` RELATIVE TO THE CWD, so when we
# run from this experiment folder it silently misses backend/.env — dropping e.g.
# OPENALEX_EMAIL (the polite pool: 10 req/s vs the throttled common pool, which would bite
# Phase 7's forward-citation snowball). OPENAI_API_KEY only survives because it happens to
# be exported to the OS env. Loading backend/.env into os.environ here makes every backend
# setting resolve no matter where the REPL/pytest is launched. config.py is imported by
# every experiment module, so this is the earliest guaranteed chokepoint.
# parents[3] of .../backend/testing/r_and_d/search_experiments/config.py is backend/.
_BACKEND_ENV = Path(__file__).resolve().parents[3] / ".env"
if _BACKEND_ENV.exists():
    # override=False: a value already exported to the shell wins over the file.
    load_dotenv(_BACKEND_ENV, override=False)
else:  # pragma: no cover - only trips if the experiment is moved without updating this
    import warnings

    warnings.warn(
        f"backend/.env not found at {_BACKEND_ENV}; backend settings may be unset"
    )


@dataclass(frozen=True)
class Models:
    """LLM/rerank model tiering (spec §2)."""

    # High-volume tier: per-paper relevance judging + keyword query rewriting.
    judge_model: str = "gpt-5.4-mini"
    keyword_rewrite_model: str = "gpt-5.4-mini"
    # Low-volume, high-leverage tier: criteria extraction, recency/centrality
    # intent, dense/boolean query (re)formulation.
    criteria_model: str = "gpt-5.5"
    intent_model: str = "gpt-5.5"
    formulation_model: str = "gpt-5.5"
    # Cohere reranker for the content blend (Arms B & C) and the §4.7 sweep.
    rerank_model: str = "rerank-english-v3.0"


@dataclass(frozen=True)
class Budgets:
    """Per-query budgets — diligent-equivalent operating point (spec §2, §4.3a)."""

    # Total per-paper judgements per arm per query (PF quota=250). Cost logged,
    # not capped (§2): the budget steers adaptive judging's stopping, but the
    # cost/recall tradeoff is itself a finding.
    judge_quota: int = 250
    # Adaptive judging budget steered *per iteration* (spec §4.3 Step 2 "~150").
    per_iteration_judge_budget: int = 150
    n_search_iterations: int = 2  # diligent: 2 retrieval iterations (§4.3a)
    n_initial_queries: int = 5  # N=5 diverse formulations (§4.3 Step 1)
    n_parametric_suggestions: int = 15  # ~10-15 LLM-named candidate papers
    snowball_top_k: int = 200  # promote top ~200 each direction (§4.3 Step 3)
    dense_top_k: int = 250  # S2 dense/snippet top-k per query (Arm C, §4.3a)
    s2_relevance_top_k: int = 250  # S2 /paper/search top-k per query (Arm C)
    final_result_cap: int = 250  # ASTA-bench ranked-list cap (§4.3 Step 5)


@dataclass(frozen=True)
class Adaptive:
    """Batched Thompson Sampling + short-circuit (PF relevance_loading_optimization.py).

    Ported verbatim from PF config.toml [default.relevance_judgement] (spec §4.3 Step 2).
    """

    uniform_preload_size: int = 5  # preload N candidates per origin before sampling
    initial_batch_size: int = 20
    batch_growth_factor: int = 2
    window_size: int = 20
    decay_factor: float = 0.95
    gaussian_variance: float = 0.1
    max_concurrency: int = 50  # <=50 concurrent judgements
    # HighlyRelevantShortcircuit: stop once >=1 Perfect found AND accumulated
    # score >= cap, scoring +2 per Perfect (=3) and +1 per Highly (=2).
    highly_relevant_cap: int = 50
    score_per_perfect: int = 2
    score_per_highly: int = 1


@dataclass(frozen=True)
class SnowballWeights:
    """Citation-snowball scoring coefficients (PF snowball_agent.py:319-365, spec §4.3/§4.3a).

    forward  = 1.0*seed_rel + 0.1*is_influential - 0.005*candidate_citation_count
    backward = 1.0*seed_rel                       - 0.0005*candidate_citation_count
    Arm B (OpenAlex) drops the 0.1*is_influential term — source-forced (§4.3 diff #2).
    """

    seed_relevance_bias: float = 1.0
    influential_bias: float = 0.1  # Arm C only; Arm B sets this to 0.0
    forward_citation_count_bias: float = -0.005
    backward_citation_count_bias: float = -0.0005


@dataclass(frozen=True)
class BlendWeights:
    """Content blend + intent->weights table (PF sorting.py, spec §4.3 Step 5)."""

    # content = rj_weight*judge + rerank_weight*cohere + snippet_weight*sigmoid(num_snippets)
    # Arm B has no snippet leg (source-forced, §4.3 diff #3) and omits snippet_weight;
    # the final blend renormalises components so the dropped 0.025 needs no rescaling.
    rj_weight: float = 0.9
    rerank_weight: float = 0.075
    snippet_weight: float = 0.025  # Arm C only

    # intent -> (w_content, w_recent, w_central). PF SortPreferences.get_scoring_weights().
    intent_weights: dict = field(
        default_factory=lambda: {
            "just_topic": (0.95, 0.025, 0.025),  # default
            "recent": (0.80, 0.175, 0.025),
            "influential": (0.80, 0.025, 0.175),
            "recent_and_influential": (0.80, 0.10, 0.10),
        }
    )


@dataclass(frozen=True)
class JudgeThresholds:
    """0-3 relevance bucketing (BENCH relevance.py calculate_0_to_3_relevance).

    weighted score s in [0,1] -> bucket: s<=0.25 ->0, <=0.67 ->1, <=0.99 ->2, else 3.
    """

    not_relevant: float = 0.25
    somewhat_relevant: float = 0.67
    highly_relevant: float = 0.99
    # Per-criterion verbal label -> numeric code (BENCH relevance.py rj_4l_codes).
    # Note: the judge prompt offers only 3 labels (Perfectly/Somewhat/Not); "Highly"
    # is retained for parity with BENCH's 4-level code map but is not emitted.
    label_codes: dict = field(
        default_factory=lambda: {
            "Perfectly Relevant": 3,
            "Highly Relevant": 2,
            "Somewhat Relevant": 1,
            "Not Relevant": 0,
        }
    )


@dataclass(frozen=True)
class Inflation:
    """Pooled-normalizer inflation factor (BENCH paper_finder_utils.py get_factor, spec §4.6).

    factor = max(min_factor, 2/ln(count)) for count>1, else max_factor.
    k_est  = ceil(count * factor).
    NB: BENCH only applies inflation to qids starting "semantic" — a dataset quirk.
    We apply it to *every* query (§4.6), so metrics.py drops that conditional.
    """

    max_factor: int = 10
    min_factor: int = 2


@dataclass(frozen=True)
class Config:
    models: Models = field(default_factory=Models)
    budgets: Budgets = field(default_factory=Budgets)
    adaptive: Adaptive = field(default_factory=Adaptive)
    snowball: SnowballWeights = field(default_factory=SnowballWeights)
    blend: BlendWeights = field(default_factory=BlendWeights)
    judge: JudgeThresholds = field(default_factory=JudgeThresholds)
    inflation: Inflation = field(default_factory=Inflation)

    # Concurrency for the per-paper judge (spec §4.5: batched, ~50-75 parallel).
    judge_concurrency: int = 50
    # Cohere rerank batch size (PF cohere.py: <=500 docs/request).
    rerank_batch_size: int = 500
    # Politeness: keep the S2 client *below* 1 req/s cumulative (spec §7, §9).
    s2_min_request_interval_s: float = 1.1


CONFIG = Config()
