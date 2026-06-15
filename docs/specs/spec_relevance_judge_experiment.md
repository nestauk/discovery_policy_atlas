# Spec: Relevance-Judge Quality Experiment (v2 vs ASTA vs human) — Phase 1b

**Status:** Agreed via design interview, 2026-06-13 (split from the combined retrieval spec)
**Owner:** Aidan Kelly
**Timebox:** ~1 week engineering + human annotation turnaround (~2 hrs annotation, splittable)
**Code location:** `scripts/research/retrieval_experiments/` (same untracked folder as the retrieval experiment)
**Companion spec:** `spec_retrieval_experiment_openalex.md` — run **first**. This spec
reuses its candidate pool, its per-query relevance criteria, and its cached LLM judgments.
**Deliverable:** Findings on whether v2's relevance rating is any good and whether the
ASTA criteria judge is better; feeds the v3 `ground`/appraise tooling decisions.

---

## 1. Motivation

The retrieval experiment freezes one relevance judge and uses it as an instrument. This
experiment turns the instrument into the subject:

> Is v2's relevance rating any good, and is the ASTA criteria-decomposed judge better —
> measured against human gold?

Why it matters: (a) v2's production judge gates what users ever see, so its false-negative
rate is a direct evidence-coverage leak independent of retrieval; (b) the retrieval
experiment's *absolute* recall numbers are only as trustworthy as its judge, and this
experiment is what licenses (or qualifies) them; (c) it tests the one assumption that
could invalidate the retrieval *ranking* — judge errors correlated with which arm
surfaced a paper.

### Why this is separable from retrieval — and runs second

A frozen judge applied identically to both retrieval arms gives a valid arm ranking even
if imperfect (retrieval spec §1). So retrieval concludes without this. This experiment
then validates the instrument. Running it **second** is the efficient order: the
expensive pooled candidates and their LLM judgments already exist (retrieval spec §4.5/4.6),
so the only new work is human annotation on a sampled subset + agreement analysis.

---

## 2. Judges compared — at their native outputs

1. **v2 additive judge** — production prompt/scoring imported from
   `backend/app/services/analysis/relevance.py` + `prompts.py:70–128`. Native output:
   boolean `is_relevant` + a 0–1 `relevance_confidence` that is **additive** (+0.2 per
   matched PICO factor), i.e. a match-count, **not** an ordinal relevance grade.
2. **ASTA criteria judge** — the retrieval spec's §4.5 judge. Native output: per-criterion
   P/S/N + a continuous weighted score, bucketed 0–3.

**v2 judge inputs — run it as production did, not on the stripped query.** `RELEVANCE_SYSTEM_PROMPT`
takes `research_question` (required) + optional `population_selected`, `outcome_selected`,
`screening_factors`, `geography`. The PICO fields are optional in code, so the judge won't
fail without them — but feeding it only the stripped free-text `query_text` (as the
retrieval arms get) would silently **degrade** it: the population/outcome/geography
prioritisation rules never fire and confidence collapses to the research-question factor
alone. That is a strawman, not v2. **So the v2 judge is run with its real production inputs
reconstructed from `original_search_context`** (exported per retrieval spec §4.1) — the same
PICO fields the wizard fed it in production. This is an *intentional, fair* asymmetry: v2
gets the structured inputs it was designed for; the ASTA judge gets criteria extracted from
free text as *it* was designed; the human gold (holistic 0–3) is judge-agnostic. Each judge
at its best, against a neutral target.

Note the forward-looking limit: in the v3 no-wizard world the v2 judge could not obtain
these PICO inputs anyway, so a decent score here does **not** make it transplantable to v3 —
itself part of the case for the ASTA-style judge.

Both score the **same human-annotated subset** of the retrieval pool, so all three
(v2, ASTA, human) judge identical (query, paper) pairs. ASTA judgments are read from the
retrieval experiment's cache; only the v2 judge is newly run here (it's a thin import).

**The two judges have different native output types, so we do NOT coerce v2 onto the
0–3 scale for the primary comparison.** That would require arbitrary cut-points, and a
0–3 target reconstructed from the criteria formula would share ASTA's structure and
unfairly advantage it. Each judge is measured against ground truth in its own terms (§5).

---

## 3. Ground truth — two human signals

Human Argilla labels (§4) are gold, in two forms:

1. **Holistic overall relevance (0–3), one per paper** — elicited *directly*,
   judge-agnostic (not reconstructed from the criteria formula). This is the **target for
   the cross-judge comparison** (v2 vs ASTA), so neither judge is scored against a target
   shaped like the other.
2. **Per-criterion P/S/N** — used **only** for ASTA criterion-level diagnosis (where ASTA
   fails), not for the v2-vs-ASTA contest.

---

## 4. Human annotation (Argilla)

Reuses the existing evidence-categorisation Argilla pattern (`setup_argilla.py`,
`export_from_argilla.py`, local `docker-compose.yaml` under
`backend/testing/r_and_d/evidence_categorisation/`).

- **Volume:** ~100 (query, paper) pairs, stratified across (a) the frozen LLM judge's
  score 0–3 and (b) use case, sampled from the retrieval pool — so the judge is checked
  across its whole range, not just easy cases. Two signals per paper ≈ ~100 holistic
  labels + ~400 per-criterion labels ≈ ~500 decisions, ~2 hrs total, splittable. The
  abstract read dominates; the clicks after it are near-free. Wider error bars than a
  200-pair set — stated in §6.
- **Multi-annotator overlap:** a ~20-pair subset assigned to 2–3 annotators (both label
  types) to measure inter-annotator agreement (the ceiling); the rest single-annotated.
- **Annotators:** **decide later** — build the datasets and records now so anyone can
  annotate; recruitment (you + 1–2 evidence colleagues likely) is a runtime detail.
- **Two datasets** (both adapt from `setup_argilla.py`):
  1. **`relevance-criteria`** — exploded (query, paper, criterion) triples (chosen over
     per-query datasets or fixed max-criteria slots: keeps management in scripted code,
     avoids per-label indirection that would corrupt the gold standard). One record = one
     criterion judgment, so settings are fixed even though criteria differ per query.
     - Fields: `query_text`, `criterion_name`, `criterion_description`, `weight`, `title`,
       `abstract` (+ `title_only` flag), `metadata` (year, venue, citations, OA).
     - Questions: one `LabelQuestion` `relevance` (Perfect/Somewhat/Not) + `TextQuestion` notes.
     - Records sorted so a paper's criteria are consecutive (read abstract once, label N).
  2. **`relevance-overall`** — one record per (query, paper), the judge-agnostic target.
     - Fields: `query_text`, `title`, `abstract` (+ `title_only` flag), `metadata`.
     - Questions: one `RatingQuestion` `overall_relevance` (0–3) + `TextQuestion` notes.
  - Annotate a paper's criteria then its overall in the same sitting (consistency).
  - Export mirrors `export_from_argilla.py` → `annotations/human_criteria.parquet` and
    `annotations/human_overall.parquet`.

The criteria, candidate pool, and ASTA judgments all come from the retrieval experiment;
this experiment adds the human labels and the v2 judgments.

---

## 5. Metrics

**Primary (threshold-free / native — no bucketing of v2):**

| Metric | What it answers |
|---|---|
| Ordinal association vs human | Spearman ρ / Kendall τ-b between each judge's **raw continuous score** (v2 confidence; ASTA pre-bucket weighted score) and the **holistic human 0–3**. No cut-points involved. |
| Screening performance vs human | each judge's **native binary decision** (v2 `is_relevant`; ASTA bucket ≥ 2) vs human-relevant (human ≥ Highly): precision / recall / F1 and **false-negative rate** — the product-relevant consequence (what gets dropped before users see it). |
| Human-vs-human ceiling | agreement on the ~20-pair overlap subset — the **ceiling** any judge can hit. |
| Judge-vs-judge | v2 vs ASTA on raw-score rank correlation + binary-decision agreement — how differently they'd screen. |
| Arm-correlated bias check | does either judge's error rate vs human differ for papers surfaced by Arm A vs Arm B? (This is the test that validates the retrieval experiment's *ranking*.) |

**Secondary (same-scale, clearly caveated):**

| Metric | What it answers |
|---|---|
| Fitted-bucket κ | quadratic-weighted κ vs holistic human 0–3, with v2's cut-points **fit to maximise agreement** (best-case mapping), cross-validated on a split to avoid overfitting ~100 points; ASTA uses its fixed buckets. Labelled "fitted thresholds." |
| Criterion-level agreement (ASTA only) | weighted κ per criterion vs human per-criterion labels — *where* ASTA fails. |
| Confusion / bias analysis | systematic skew (e.g. v2 over-crediting query-vocabulary echo; either judge under-crediting title-only papers). |

A judge is only credited as "better" if its advantage clears the human–human ceiling and
the (~100-pair) error bars; a smaller gap is reported as inconclusive, not a win.

---

## 6. Harness additions

Builds on the retrieval experiment's folder; new pieces only:

```
scripts/research/retrieval_experiments/
  judges/
    v2_judge.py            # imports backend relevance service; runs over the annotated subset
  annotation/
    setup_argilla.py       # the two relevance datasets (adapted from evidence_categorisation)
    export_argilla.py
  metrics/
    agreement.py           # weighted kappa, Spearman/Kendall, screening P/R/F1 + FN-rate, arm-bias check
  annotations/             # human_criteria.parquet, human_overall.parquet
```

The ASTA judgments and the relevance criteria are read from the retrieval experiment's
`judgements/` cache and `queries.jsonl` — not recomputed.

---

## 7. Execution plan (~1 week + annotation turnaround)

1. Sample + stratify the ~100-pair annotation set from the retrieval pool — day 1
2. Build the two Argilla datasets, seed records, stand up local Argilla — day 1–2
3. Run the v2 judge over the annotated subset (ASTA judgments already cached) — day 2
4. Annotation collection (parallel / async — the gating dependency) — days 2–N
5. Agreement metrics + bias check + report once labels land — day N+1

---

## 8. Risks & limitations (pre-registered)

- **~100-pair sample:** agreement statistics carry wider error bars, and the ~20-pair
  ceiling subset gives a rough human-ceiling estimate. Sufficient to rank the judges and
  diagnose criterion-level failure modes directionally; not to certify small differences.
  Treat margins inside the error bars as ties.
- **Annotator recruitment deferred:** the gold standard's strength depends on who
  annotates and how many do the overlap; with a single annotator the human ceiling can't
  be measured and conclusions weaken to single-rater agreement.
- **Holistic-vs-criteria target choice:** the judge-agnostic holistic label is the right
  cross-judge target, but it's a coarser signal than the criteria rollup; criterion-level
  conclusions therefore apply to the ASTA judge only.
- **v2 confidence is a match-count, not a grade:** even with fitted thresholds the
  same-scale κ flatters v2's intended use; the native binary screening metric is the
  fairer headline for it.

## 9. Prerequisites

- The retrieval experiment (`spec_retrieval_experiment_openalex.md`) run to the point of a
  populated `judgements/` cache + `queries.jsonl` + per-query criteria
- Local Argilla instance (reuse `evidence_categorisation/docker-compose.yaml`)
- Backend importable for the v2 relevance service
- 2–3 annotators (decided at runtime)
