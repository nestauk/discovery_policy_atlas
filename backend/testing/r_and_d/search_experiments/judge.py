"""The frozen relevance judge — the experiment's measuring instrument (spec §4.5).

This judge is *used*, not *validated*, here: a single frozen instrument applied
identically to every arm so the A→B→C ranking is valid even if the judge is imperfect.
Its own quality is the companion judge spec's subject — which reuses this module's cache.

Two LLM steps, both ported from the source repos (mechanisms → PF, scoring → BENCH):

  1. Per-query criteria extraction (gpt-5.5, once per query, ARM-INDEPENDENT).
     Port of PF `_identify_relevance_criteria_prompt_tmpl`
     (asta-paper-finder query_analyzer_prompts.py:486). Decomposes the free-text research
     question into weighted, content-only criteria {name, description, weight} summing to 1.
     A function of the query, NOT the retrieval method — so the *same* criteria are applied
     to every arm's candidates (this is why Arm A needs no criteria step of its own).
     We keep only PF's *required* criteria and drop its nice_to_have / clarification-question
     branches (KISS — the BENCH score only consumes weight-sum-to-1 criteria).

  2. Per-paper judging (gpt-5.4-mini, batched, resumable).
     Port of BENCH `relevance_criteria_judgement_prompt_with_relevant_snippets_after`
     (asta-bench relevance.py:61). Per criterion: one of {Perfectly, Somewhat, Not}
     Relevant + a verbatim ≤20-word snippet; plus a ≤30-word summary. Scored by
     `metrics.relevance_criteria_score` -> `metrics.bucket_0_to_3` (the SAME functions the
     recall metric is built on — no second copy of the formula).

Caching (spec §4.5): every judgement keyed by (query_id, paper_id) and persisted, so a
paper pooled across arms + normalizer runs is judged exactly once. Layout:

    results/judgements/criteria/{query_id}.json   # extracted criteria, one file per query
    results/judgements/raw/{query_id}.jsonl       # LLMProcessor output, resumable shard
    results/judgements/judgements.parquet         # consolidated cache, the metric's input

REPL usage (no main(), no argparse — spec conventions):
    import asyncio
    from judge import extract_criteria, judge_papers, load_judgements, get_cached_levels
    crit = extract_criteria("q001", "RCTs on universal basic income and employment")
    papers = [{"paper_id": "W1", "title": "...", "abstract": "..."}]
    df = asyncio.run(judge_papers("q001", "RCTs on UBI...", papers))
    levels = get_cached_levels("q001")   # {paper_id: 0..3} — feed straight into metrics.py

Backend helpers (LLMProcessor, get_llm) are lazy-imported inside the LLM-calling
functions so the pure logic here stays importable/testable without backend env vars.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from config import CONFIG
from metrics import bucket_0_to_3, relevance_criteria_score

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paths — the shared judgement cache (consumed by metrics, the report, and the
# companion judge spec).
# --------------------------------------------------------------------------- #
RESULTS_DIR = Path(__file__).parent / "results"
JUDGE_DIR = RESULTS_DIR / "judgements"
CRITERIA_DIR = JUDGE_DIR / "criteria"
RAW_DIR = JUDGE_DIR / "raw"
JUDGEMENTS_PARQUET = JUDGE_DIR / "judgements.parquet"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class RelevanceCriterion(BaseModel):
    """One weighted relevance criterion (PF RelevanceCriterion; BENCH equivalent)."""

    name: str = Field(description="Short distinct name for the criterion.")
    description: str = Field(
        description="What a paper must say to satisfy this criterion (content only)."
    )
    weight: float = Field(
        description="Importance in [0,1]; weights across required criteria sum to 1."
    )


class CriteriaSet(BaseModel):
    """Structured-output target for criteria extraction (PF required criteria only)."""

    criteria: list[RelevanceCriterion] = Field(
        description="The required relevance criteria; weights should sum to ~1."
    )


# --------------------------------------------------------------------------- #
# Prompts (ported — see module docstring for source files)
# --------------------------------------------------------------------------- #
# PF _identify_relevance_criteria_prompt_tmpl, trimmed to the required-criteria path
# (we don't ask clarification questions — queries are curated, the instrument is frozen).
CRITERIA_SYSTEM_PROMPT = """\
You are an expert research and policy analyst. The research question below comes from a \
policy-research / evidence-synthesis context (a researcher gathering evidence to inform a \
policy question). Identify a set of relevance criteria for it; these will be used to judge \
how relevant specific papers are, then to rank and filter them.

Capture the substantive dimensions the QUESTION ITSELF expresses — the intervention or \
policy, the population or group, the setting or context, and the outcome(s) of interest — \
as content criteria. (Where the question states a geography or population, treat it as part \
of the topic, not as a hard filter: a paper from another setting whose findings plainly \
bear on the question is still relevant.)

Make sure not to lose necessary RELATIONS between criteria. For example, for "effect of \
free school meals on attainment", criteria "free school meals" and "attainment" alone would \
wrongly accept a paper mentioning both but not the *effect of one on the other*. Capture \
the relation either with a heavily-weighted relation criterion or by folding the relation \
into each description.

Criteria must refer ONLY to the CONTENT of the paper. IGNORE all metadata:
- author/coauthor names
- years or time words ("recent", "latest")
- impact words ("central", "seminal", "influential")
- venues (e.g. journal or conference names)
Do NOT make study design or evidence type (e.g. RCT, systematic review) a criterion — \
relevance is about topical bearing on the question, not the strength or pedigree of the \
evidence.

Return a list of criteria; each has a `name`, a `description`, and a `weight` in [0, 1]. \
The weights should sum to 1. Prefer a small number of criteria (typically 2-5) that \
together capture what makes a paper genuinely on-topic for this question."""

# BENCH relevance_criteria_judgement_prompt_with_relevant_snippets_after, adapted to a
# flat per-criterion schema (LLMProcessor builds the structured schema from output_fields,
# so this message explains the task + criteria; field-level rules are reinforced by the
# auto-appended output-field descriptions).
JUDGE_SYSTEM_PROMPT_HEADER = """\
You are an expert research and policy analyst assessing whether a paper provides evidence \
that bears on a policy research question, decomposed into the criteria below.

Judge how relevant the following paper is to EACH of the provided criteria, considering \
the whole description of each criterion. Judge ONLY on the paper's content (title + \
abstract); do not reward metadata, study design, or evidence type — only topical bearing \
on each criterion. Consider related concepts and transferable findings, not just exact \
keyword matches.

For each criterion give a relevance label — exactly one of "Perfectly Relevant", \
"Somewhat Relevant", "Not Relevant" — and a `relevant_snippet`: ONE short verbatim span \
(copy EXACT text, up to 20 words) that concretely shows the relevance, or an empty string \
if Not Relevant. Also give a `relevance_summary`: an actionable summary (up to 30 words) \
of how the paper is relevant overall, starting with the strongest matches; empty if not \
relevant to any criterion.

The criteria, in order, are:
{criteria_block}"""


# --------------------------------------------------------------------------- #
# Criteria extraction (gpt-5.5, once per query, cached)
# --------------------------------------------------------------------------- #
def _read_criteria_file(path: Path) -> list[RelevanceCriterion]:
    """Parse a cached criteria JSON file -> RelevanceCriterion list (no path checks)."""
    payload = json.loads(path.read_text())
    return [RelevanceCriterion(**c) for c in payload["criteria"]]


def load_criteria(query_id: str) -> list[RelevanceCriterion]:
    """Read cached criteria for a query (no LLM). Raises if not yet extracted."""
    path = CRITERIA_DIR / f"{query_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No cached criteria for query {query_id!r} at {path}. "
            f"Run extract_criteria({query_id!r}, query_text) first."
        )
    return _read_criteria_file(path)


def _normalise_weights(criteria: list[RelevanceCriterion]) -> list[RelevanceCriterion]:
    """Defensive: renormalise weights to sum to 1 (the LLM occasionally drifts to 0.99).

    BENCH's score assumes weights sum to 1; an off-by-epsilon sum would skew every bucket.
    """
    total = sum(c.weight for c in criteria)
    if total <= 0:
        raise ValueError(f"criteria weights sum to {total}; cannot normalise")
    if abs(total - 1.0) > 1e-6:
        logger.warning("Criteria weights sum to %.4f; renormalising to 1.0", total)
        return [c.model_copy(update={"weight": c.weight / total}) for c in criteria]
    return criteria


def extract_criteria(
    query_id: str, query_text: str, *, force: bool = False
) -> list[RelevanceCriterion]:
    """Extract weighted, content-only relevance criteria for a query (cached to disk).

    Frozen instrument => temperature 0. Result reused by every arm, the reformulation
    loop, the report, and the companion judge spec.
    """
    CRITERIA_DIR.mkdir(parents=True, exist_ok=True)
    path = CRITERIA_DIR / f"{query_id}.json"
    if path.exists() and not force:
        logger.info("Criteria cache hit for query %s", query_id)
        return load_criteria(query_id)

    # Lazy import: pulls backend settings/env, so keep it out of module import.
    from langchain_core.prompts import ChatPromptTemplate

    from app.utils.llm.llm_utils import get_llm

    logger.info(
        "Extracting criteria for query %s (model=%s)",
        query_id,
        CONFIG.models.criteria_model,
    )
    llm = get_llm(CONFIG.models.criteria_model, 0.0).with_structured_output(CriteriaSet)
    prompt = ChatPromptTemplate.from_messages(
        [("system", CRITERIA_SYSTEM_PROMPT), ("user", "{query}")]
    )
    result: CriteriaSet = llm.invoke(prompt.format(query=query_text))
    criteria = _normalise_weights(result.criteria)

    path.write_text(
        json.dumps(
            {
                "query_id": query_id,
                "query_text": query_text,
                "model": CONFIG.models.criteria_model,
                "criteria": [c.model_dump() for c in criteria],
            },
            indent=2,
        )
    )
    logger.info(
        "Extracted %d criteria for query %s: %s",
        len(criteria),
        query_id,
        [c.name for c in criteria],
    )
    return criteria


# --------------------------------------------------------------------------- #
# Per-paper judging schema construction (pure — offline-testable)
# --------------------------------------------------------------------------- #
_LABELS = '"Perfectly Relevant", "Somewhat Relevant", or "Not Relevant"'


def build_output_fields(criteria: list[RelevanceCriterion]) -> list[dict[str, str]]:
    """Build LLMProcessor `output_fields` dynamically from a query's criteria.

    Flat fields (criterion_{i}_relevance / criterion_{i}_snippet + relevance_summary) are
    how we fit BENCH's nested per-criterion output into LLMProcessor's create_model schema.
    Index-keyed names stay valid identifiers regardless of the criterion's prose name.
    """
    fields: list[dict[str, str]] = []
    for i, c in enumerate(criteria, 1):
        fields.append(
            {
                "name": f"criterion_{i}_relevance",
                "type": "str",
                "description": (
                    f"Relevance to criterion '{c.name}' ({c.description}). "
                    f"Answer EXACTLY one of: {_LABELS}."
                ),
            }
        )
        fields.append(
            {
                "name": f"criterion_{i}_snippet",
                "type": "str",
                "description": (
                    f"Verbatim span (<=20 words, copied exactly) showing relevance to "
                    f"'{c.name}'; empty string if Not Relevant."
                ),
            }
        )
    fields.append(
        {
            "name": "relevance_summary",
            "type": "str",
            "description": "Actionable <=30-word summary of overall relevance; empty if none.",
        }
    )
    return fields


def _build_judge_system_message(criteria: list[RelevanceCriterion]) -> str:
    block = "\n".join(
        f"  {i}. {c.name} (weight {c.weight:.3f}): {c.description}"
        for i, c in enumerate(criteria, 1)
    )
    return JUDGE_SYSTEM_PROMPT_HEADER.format(criteria_block=block)


def _format_paper(paper: dict) -> str:
    """Render a candidate paper to judge-prompt text (title + abstract + enrichment flag)."""
    title = paper.get("title") or "No title"
    abstract = paper.get("abstract") or ""
    title_only = (not abstract) or paper.get("text_basis") == "title_only"
    flag = " [TITLE ONLY — no abstract available]" if title_only else ""
    body = abstract or "No abstract available."
    return f"Title: {title}{flag}\n\nAbstract: {body}"


# --------------------------------------------------------------------------- #
# Scoring a raw judgement row (pure — offline-testable)
# --------------------------------------------------------------------------- #
def score_row(
    row: dict, criteria: list[RelevanceCriterion]
) -> tuple[list[int], float, int]:
    """Map one raw LLMProcessor row -> (per-criterion codes, weighted score, 0–3 level).

    Per-criterion label -> code via CONFIG.judge.label_codes; unknown/missing label is
    treated as Not Relevant (0) with a warning so a single malformed field can't crash a run.
    """
    codes: list[int] = []
    for i in range(1, len(criteria) + 1):
        label = row.get(f"criterion_{i}_relevance")
        code = CONFIG.judge.label_codes.get(label)
        if code is None:
            logger.warning(
                "Unrecognised relevance label %r for %s criterion %d; treating as Not Relevant",
                label,
                row.get("id"),
                i,
            )
            code = 0
        codes.append(code)
    weights = [c.weight for c in criteria]
    score = relevance_criteria_score(weights, codes)
    return codes, score, bucket_0_to_3(score)


# --------------------------------------------------------------------------- #
# Per-paper judging (gpt-5.4-mini, batched + resumable via LLMProcessor)
# --------------------------------------------------------------------------- #
async def judge_papers(
    query_id: str,
    query_text: str,
    papers: list[dict],
    *,
    criteria: list[RelevanceCriterion] | None = None,
    batch_size: int | None = None,
) -> pd.DataFrame:
    """Judge a batch of candidate papers for one query; append to the resumable shard.

    Papers already in the query's JSONL shard are skipped (LLMProcessor resume) — this is
    what lets the adaptive judging loop (Phase 3) call this incrementally and what makes
    cross-arm pooling judge each paper once. Returns the consolidated judgement rows for
    this query.

    Each paper dict needs `paper_id`, `title`, `abstract` (optional `text_basis`).
    NOTE: the spec's "minimal reasoning" for gpt-5.4-mini is not wired — backend get_llm
    does not expose reasoning_effort. Model name is set from CONFIG; effort is deferred.
    """
    criteria = criteria or extract_criteria(query_id, query_text)
    if not papers:
        logger.info("No papers to judge for query %s", query_id)
        return load_judgements([query_id], write_parquet=False)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    shard = RAW_DIR / f"{query_id}.jsonl"

    # Lazy import: pulls backend settings/env.
    from app.utils.llm.batch_check import LLMProcessor

    processor = LLMProcessor(
        model_name=CONFIG.models.judge_model,
        output_path=str(shard),
        system_message=_build_judge_system_message(criteria),
        output_fields=build_output_fields(criteria),
        run_name="search_exp.judge",
    )
    text_data = {str(p["paper_id"]): _format_paper(p) for p in papers}
    logger.info(
        "Judging %d candidate(s) for query %s (model=%s, batch=%d)",
        len(text_data),
        query_id,
        CONFIG.models.judge_model,
        batch_size or CONFIG.judge_concurrency,
    )
    await processor.process_text_data(
        text_data,
        batch_size=batch_size or CONFIG.judge_concurrency,
        sleep_time=0.0,
    )
    return load_judgements([query_id])


# --------------------------------------------------------------------------- #
# Cache consolidation (pure given dirs — offline-testable)
# --------------------------------------------------------------------------- #
def _consolidate(
    raw_dir: Path, criteria_dir: Path, query_ids: list[str] | None = None
) -> pd.DataFrame:
    """Read raw JSONL shards + cached criteria -> scored judgement rows (DataFrame).

    One row per (query_id, paper_id) with the final 0–3 `level`, the weighted `score`, the
    per-criterion `codes`, and the supporting `summary`/model metadata.
    """
    shards = sorted(raw_dir.glob("*.jsonl")) if raw_dir.exists() else []
    if query_ids is not None:
        wanted = set(query_ids)
        shards = [s for s in shards if s.stem in wanted]

    records: list[dict] = []
    for shard in shards:
        qid = shard.stem
        criteria = _read_criteria_file(criteria_dir / f"{qid}.json")
        raw = pd.read_json(shard, lines=True)
        if raw.empty:
            continue
        for row in raw.to_dict("records"):
            codes, score, level = score_row(row, criteria)
            records.append(
                {
                    "query_id": qid,
                    "paper_id": str(row["id"]),
                    "level": level,
                    "score": score,
                    "codes": codes,
                    "summary": row.get("relevance_summary"),
                    "model": row.get("model"),
                    "timestamp": row.get("timestamp"),
                }
            )

    cols = [
        "query_id",
        "paper_id",
        "level",
        "score",
        "codes",
        "summary",
        "model",
        "timestamp",
    ]
    df = pd.DataFrame.from_records(records, columns=cols)
    logger.info(
        "Consolidated %d judgement row(s) from %d shard(s)", len(df), len(shards)
    )
    return df


def load_judgements(
    query_ids: list[str] | None = None, *, write_parquet: bool = True
) -> pd.DataFrame:
    """Consolidate the judgement cache to a DataFrame (and optionally the parquet snapshot).

    `query_ids=None` loads every shard. The parquet is always the full cache, never a
    single-query slice, so callers can't accidentally truncate the shared artefact.
    """
    df = _consolidate(RAW_DIR, CRITERIA_DIR, query_ids)
    if write_parquet and query_ids is None and not df.empty:
        JUDGE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(JUDGEMENTS_PARQUET, index=False)
        logger.info(
            "Wrote judgement cache -> %s (%d rows)", JUDGEMENTS_PARQUET, len(df)
        )
    return df


def get_cached_levels(query_id: str) -> dict[str, int]:
    """Return {paper_id: 0–3 level} for one query — the direct input to metrics.py."""
    df = _consolidate(RAW_DIR, CRITERIA_DIR, [query_id])
    return dict(zip(df["paper_id"], df["level"]))
