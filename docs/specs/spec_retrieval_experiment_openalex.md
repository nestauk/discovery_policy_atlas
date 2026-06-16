# Spec: Retrieval Experiment (ASTA-inspired) — Phase 1

**Status:** Agreed via design interview, 2026-06-12 (split from the combined spec 2026-06-13). **Rev. 2026-06-15:** added **Arm C** — a faithful Paper Finder agent on the Semantic Scholar (S2) API, now that S2 access is available (§4.3a); related edits throughout (§2, §3, §4.4–4.7, §5–9).
**Owner:** Aidan Kelly
**Timebox:** ~3 weeks, one person — **all three arms built and evaluated together** as one three-way deliverable (the A→B→C ladder). The agentic core is built once (source-agnostic) and reused across Arms B and C; Arm A is a thin baseline wrapper (§6).
**Code location:** `backend/testing/r_and_d/search_experiments/` (untracked research folder, alongside the other `r_and_d` experiments — not part of the deployable repo). *Rev. 2026-06-15: relocated here from `scripts/research/retrieval_experiments/` so it sits with `evidence_categorisation`/`boolean_queries` and can consume the backend package as an editable path dep.*
**Deliverable:** Findings report + team session; direct input to the v3 `retrieve` tool spec
**Companion spec:** `spec_relevance_judge_experiment.md` — evaluates the *quality* of the relevance judge this experiment uses as an instrument. Run **after** this one (it reuses this experiment's candidate pool + cached judgments).

---

## 1. Motivation

Policy Atlas's evidence coverage is suspected to be suboptimal because retrieval is a
single open-loop pass: one LLM-generated boolean query → OpenAlex (~200 results) →
LLM relevance screen → done. Nothing ever re-queries, expands, or learns from what was
found. AI2's ASTA paper-finder (`~/nesta/discovery/discovery_ai2_paper_agent`)
demonstrates a substantially more sophisticated closed-loop architecture, and ASTA-bench
(`.../asta-bench`) provides a principled way to measure retrieval quality without
exhaustive gold sets.

**The question:**

> Does a paper-finder-inspired ensemble retrieval pipeline materially improve evidence
> coverage (recall) over the v2 baseline on real Policy Atlas queries, and at what cost?

The output feeds the v3 backend design — specifically what the `retrieve` facade tool
(v3 brief §4) should contain and at what operating point. This is research code: nothing
here ships to production.

### The judge is an instrument here, not the subject

Recall requires a relevance judge to define what counts as relevant. This experiment
**freezes one judge (the ASTA-style criteria judge, §6) and uses it as a fixed
instrument** applied identically to every arm. Crucially:

- A frozen judge applied the same way to all arms yields a valid **ranking** of arms
  even if the judge is imperfect — provided its errors aren't correlated with which arm
  surfaced a paper. So this experiment can reach a conclusion ("ensemble beats baseline
  by X") on the LLM judge alone, **with no human annotation in the loop.**
- What it *cannot* do alone is certify the **absolute** recall numbers, or rule out the
  judge-bias-correlated-with-arm risk. Both are the job of the companion judge spec,
  which validates the instrument against human labels using this experiment's own pool.

---

## 2. Scope decisions (interview log)

| Decision | Choice |
|---|---|
| Sources | **OpenAlex** for Arms A/B. **Arm C adds Semantic Scholar** (now available) as a full second source — hosted dense/snippet search, citation graph with an influential-citation signal, abstracts + TLDR. Overton stays phase 2 (cheap levers only). Harness stays source-agnostic. |
| Dense/semantic infra | **No index built by us.** Arms A/B use OpenAlex's hosted search + `relevance_score` only; recall gains come from query diversity, reformulation, citation-graph traversal. **Arm C uses S2's hosted snippet (dense) search** as a candidate generator — still no *owned* embedding index, consistent with "no local infra." |
| Arms | **Three arms forming a ladder:** A = v2 baseline (OpenAlex) → B = full Paper Finder machinery on OpenAlex → C = the same machinery on S2. **B and C are mechanism-identical except where OpenAlex can't follow** (§4.3). **A→B isolates the machinery; B→C isolates the source.** Per-result origin tags (§4.7) decompose the source bundle within C. |
| Judge (instrument) | **ASTA-style**, frozen; criteria extracted from the free-text research question alone — *not* PICO wizard fields, because v3 is moving away from the guided search wizard. Its *quality* is out of scope here (companion spec). |
| Ground truth | **Pooled normalizer + frozen LLM judge** (ASTA-bench style), padded with normalizer-only lenient runs (§4.6). **No human annotation in this experiment.** |
| Query intelligence | **Ensemble-side (2 calls):** content extraction + recency/centrality intent. **Judge-side (1 call, arm-independent):** weighted-criteria extraction, applied to every arm (§4.5). No routing; every query treated as broad-by-description. Specific-paper / metadata-only flows out of scope. |
| Ranking blend | **Content + recency + centrality, intent-driven weights** (paper-finder style, §4.3 step 5). **Both B and C** use `0.9·judge + 0.075·Cohere-rerank`; **Arm C adds `+ 0.025·snippet-count`** (snippets are source-forced — Arm B has none). The reranker/snippet terms are also isolated post-hoc in §4.7. |
| Headline metric | **Recall@k_est** (coverage objective). nDCG, precision, adjusted F1, ranking-weight sensitivity reported as secondaries. |
| Budget per query | **Diligent-like**: ~2 retrieval iterations, snowballing, up to ~250–300 judged candidates per arm per query. Cost logged, not capped — the cost/recall tradeoff is a finding. |
| Models | **gpt-5.4-mini (minimal reasoning)** for per-paper relevance judging + keyword query rewriting (high-volume tier). **gpt-5.5** for criteria extraction, recency/centrality intent + query reformulation (low-volume, high-leverage). **Cohere `rerank-english-v3.0`** for the Arm B & C content blend + the §4.7 sweep. All frozen for the experiment's duration. |
| Missing abstracts | **Arms A/B (OpenAlex):** unchanged — **Crossref-by-DOI MVP** + Europe-PMC measured trigger (§4.4). **Arm C (S2):** abstracts/TLDR/snippets come natively from S2, so the title-only constraint largely lifts for that arm. Log title-only fraction + hit rate per arm. |
| Query set | **~20–30 real user search contexts from production DB export**, stratified by use case and expected literature density. |
| Harness | **Lightweight custom** (pandas + REPL-style `run_xxx()` helpers, matching `backend/testing/r_and_d/evidence_categorisation/` conventions). ASTA-bench metric formulas reimplemented (~100 lines) with parity unit tests — no inspect-ai dependency. |
| v2 baseline definition | **Production defaults, shared judge** (§4.2). |

---

## 3. Background references

> **Source repos (the implementing agent must follow these precisely).** Two checkouts under
> `~/nesta/discovery/discovery_ai2_paper_agent/`:
> - **PF** = `asta-paper-finder` — the *agent*. Source of truth for every **mechanism**:
>   query analysis, dense formulation/reformulation, snowball scoring, adaptive judging,
>   short-circuit, ranking blend, Cohere reranker.
> - **BENCH** = `asta-bench` — the *benchmark*. Source of truth for every **metric/scoring
>   definition**: recall@k_est, k_est inflation, corrected nDCG, F1, precision, 0–3 bucketing.
>
> Rule of thumb: **mechanisms → PF, metrics → BENCH.** The relevance judge exists in both; we
> port **BENCH**'s scoring/bucketing (§4.5) because that is what the recall metric is built on,
> with our own frozen models (§2). Paths below are repo-relative to PF or BENCH as tagged.

### v2 baseline (this repo)
- Boolean query prompt: `backend/app/services/analysis/prompts.py:13–41`
- Query generation: `backend/app/services/analysis/references.py:142–200` (single, temp 0) and `:244–360` (multi)
- OpenAlex search: `backend/app/services/openalex.py:71–280` (abstracts reinverted via PyAlex; `relevance_score`, `cited_by_count`, `publication_year`, `referenced_works` returned)
- SR/RCT fanout variants: `references.py:495–518`; dedupe `references.py:837–845`
- Existing search eval (fuzzy bibliography match): `backend/testing/evals/blueprint_comparison/search/evaluate_search.py`

### ASTA paper-finder — **PF** = `~/nesta/discovery/discovery_ai2_paper_agent/asta-paper-finder`
- Query analyzer (11 parallel extractions; **we port only content + recency + centrality**): `agents/mabool/api/mabool/agents/query_analyzer/`. The rule-based **router** + specific/by-author/metadata workflows in `agents/paper_finder/paper_finder_agent.py` are **deliberately not ported** — Arm C is broad-by-description only (§4.3a)
- Broad search orchestration (2 iterations, multi-source): `agents/.../complex_search/broad_search.py`
- Dense query reformulation prompts (we adapt the *reformulation* idea, not the dense backend): `agents/.../dense/formulation.py`
- Snowballing (forward/backward/snippet): `agents/.../snowball/snowball_agent.py` — scoring: `seed_relevance × 1.0 + influential_citations + citation_count`, top-k promotion (200)
- LLM parametric suggestions + grounding: `agents/.../llm_suggestion/`
- Relevance judgment (per-criterion, snippet evidence): `agents/.../common/computed_fields/relevance.py`
- Final ranking blend + intent→weights table: `agents/.../common/sorting.py` (SortPreferences); content blend `content_relevance_score()` = `0.9·rj + 0.075·cohere_rerank + 0.025·sigmoid(num_snippets)`
- S2 fetchers/loaders (relevance `/paper/search`, snippet `/snippet/search`, `/citations`, `/references`, `/paper/batch`): `libs/dcollection/ai2i/dcollection/fetchers/s2.py`, `.../loaders/s2_rest.py`
- Dense/snippet retrieval + formulation/reformulation prompts: `agents/.../dense/dense_agent.py`, `.../dense/formulation_prompts.py` (`_dense_formulation_prompt_multiple_tmpl`, `_dense_reformulate_prompt_tmpl`); snippet backend `.../external_api/dense/vespa.py`
- Snowball scoring (forward `1.0·seed_rel + 0.1·is_influential − 0.005·cite_count`; backward `1.0·seed_rel − 0.0005·cite_count`, no influential bias; top-k 200 each): `agents/.../snowball/snowball_agent.py:319–365`
- Agentic loop — adaptive judging (Batched Thompson Sampling), `HighlyRelevantShortcircuit` (≥1 Perfect AND Σ score ≥ 50; +2/Perfect, +1/Somewhat), quota 250: `agents/.../dense/relevance_loading_optimization.py`; diligent vs fast config: `conf/config.toml`, `conf/config.extra.fast_mode.toml`
- Cohere reranker client (`rerank-english-v3.0`, batched ≤500/req): `agents/.../external_api/rerank/cohere.py`

### ASTA-bench — **BENCH** = `~/nesta/discovery/discovery_ai2_paper_agent/asta-bench`
- Metrics: `astabench/evals/paper_finder/eval.py` — `calc_recall_at_k` (:117–153), lower-bound-corrected nDCG (:173–182), `calc_adjusted_f1` (:193)
- Judging pipeline + 0–3 bucketing: `astabench/evals/paper_finder/relevance.py:115`
- Normalizer inflation factor: `max(2, 2/ln(count))`, capped at 10 — `paper_finder_utils.py:146–196`
- Anti-gaming: 250-result cap, verbatim evidence snippets required
- Inflation factor `get_factor()` = `max(2, 2/ln(count))` for count>1 else `max_factor=10`; `k_est = ceil(count × factor)` (`paper_finder_utils.py:154–196`). Worked: count 1→×10→**10**, 2→×2.885→**6**, 3→×2→**6**, 5→×2→**10**, 10→×2→**20**, 100→×2→**200** (only count=2 exceeds the ×2 floor; the ×10 cap only ever bites at count=1)
- nDCG `lower_bound_corrected_ndcg()` + DCG `find_dcg()`: `eval.py:166–182`; adjusted-F1 = harmonic-mean(recall@k_est, nDCG), `calc_adjusted_f1()` `eval.py:193`; recall **and** precision count **Perfect (=3) only** (`count_relevant`, `eval.py:88–101`)
- S2 use in the bench itself is diagnostic only (`/paper/batch` for publication dates in the post-hoc cutoff audit, `paper_finder_utils.py:67–91`); scoring matches papers by raw `corpusId` string, no S2 resolution

---

## 4. Experiment design

### 4.1 Inputs: the query set

- **Source:** export `search_query` JSONB from `analysis_projects` in production Postgres.
  Exclude internal-team projects (reuse the exclusion logic from
  `scripts/product_analytics/user_type_metrics_exclude_internal_team.py`).
- **Curation:** manually select ~20–30, stratified by:
  - use case (`policy_blueprint`, `horizon_scan`, …)
  - expected literature density (well-studied vs sparse topics)
- **Input format per query:** the free-text research question is the arm input.
  Where a production research question is terse and essential context lives only in
  PICO fields (geography, population), rewrite the query text to fold that context in
  as natural language — this mirrors what v3's conversational users will actually type.
  Record both the original SearchContext and the curated query text.
- PICO fields are **retained as metadata** for analysis but are **not fed to arms or judge**.
- Store as `queries/queries.jsonl`: `{query_id, query_text, use_case, original_search_context, notes}`.

### 4.2 Arm A — v2 baseline (frozen)

Production defaults, invoked through the real backend code (imported, not reimplemented):

- Single boolean query, `temperature=0`, current production `BOOLEAN_QUERY_MODEL`
- SR/RCT fanout per current `OPENALEX_ENABLE_RCT_SYSREV_FANOUT` setting
- `max_results=200`, `DEFAULT_MIN_CITATIONS` as configured
- Dedupe exactly as production (`doc_id` hash)
- **v2's own relevance screen is NOT applied** — results are scored by the frozen
  experiment judge (§4.5), isolating retrieval quality from judging quality. (Whether v2's
  judge is any good is the companion judge spec's question, not this one's.)

Note: the baseline consumes the curated query text via the same prompt path production
uses (research question slot); other SearchContext fields left empty, consistent with
the v3 no-wizard direction. Flag in the report that this slightly disadvantages
baseline vs production-with-wizard; an optional sensitivity run *with* the original
SearchContext can pre-empt that objection.

### 4.3 Arm B — full Paper Finder machinery on OpenAlex

Arm B ports the **same** Paper Finder broad-search machinery as Arm C (PF:
`agents/.../complex_search/broad_search.py`, `BroadSearchAgent`) onto OpenAlex. **It is
mechanism-identical to Arm C except where OpenAlex literally cannot follow S2** — the four
source-forced differences listed at the end of this section. **Every candidate carries an
`origins` set** (mechanism + iteration) for per-mechanism attribution — PF's
`DocumentCollection` merges origins on dedupe.

> **Why identical — the A→B→C ladder.** A and B share a corpus (OpenAlex), so **A→B isolates
> the agentic machinery** (adaptive judging, snowball, reformulation, reranker) with the corpus
> held fixed. B and C share machinery, so **B→C isolates the source** (S2 corpus + the
> capabilities OpenAlex can't do). Leaving any *incidental* B/C difference in would collapse
> both clean single-variable steps into multi-variable ones — so B mirrors C wherever the API
> allows.

**Step 0 — Ensemble-specific query analysis (gpt-5.5, 2 calls):**
1. *Content extraction* — strip non-topical noise, isolate the topical core
   (port of `_content_extraction_prompt_tmpl`). Feeds this arm's query generation (Step 1).
2. *Recency/centrality intent* — classify whether the query wants recent and/or
   influential work, and any explicit time range (port of paper-finder's recency +
   centrality extractions). Drives this arm's ranking weights (Step 5).

(Weighted relevance criteria are **not** extracted here — they belong to the judge, which
applies them to *every* arm. See §4.5.)

**Step 1 — Initial retrieval (parallel):**
- *Multi-query keyword search:* gpt-5.5 generates N=5 diverse OpenAlex query
  formulations; each retrieved at `per_page=200`. Adapt paper-finder's formulation
  principles (diverse angles, no "papers about" phrasing) to OpenAlex syntax.
- *LLM parametric suggestions:* gpt-5.5 names ~10–15 candidate papers (title + year)
  from memory; each grounded against OpenAlex by title search (±2-year window) and
  DOI where given; ungrounded suggestions dropped. (Expect weaker performance on
  policy literature than CS — worth measuring, cheap to run.)

**Step 2 — Judge pass 1 (adaptive — identical to Arm C):** dedupe (OpenAlex ID, then DOI),
enrich missing abstracts (§4.4), then judge **adaptively** — port PF's `adaptive_load`
(PF: `agents/.../dense/relevance_loading_optimization.py`): uniform-preload 5 candidates per
origin, then Batched Thompson Sampling (`initial_batch_size=20`, `batch_growth_factor=2`,
`window_size=20`, `decay_factor=0.95`, ≤50 concurrent) over the per-iteration budget (~150),
stopping when spent or the short-circuit fires (§4.5). *(Replaces the old
judge-by-`relevance_score`-rank order — an incidental difference from Arm C, removed.)*

**Step 3 — Expansion (parallel):**
- *Citation snowballing* from seeds = papers judged ≥2 (Highly/Perfect):
  - backward: `referenced_works` (already on the OpenAlex work record — free)
  - forward: `filter=cites:W...` per seed (paginated; respect rate limits)
  - score with **PF's formula minus the influence term** (PF:
    `agents/.../snowball/snowball_agent.py:319–365`): forward
    `1.0·seed_relevance − 0.005·candidate_citation_count`, backward
    `1.0·seed_relevance − 0.0005·candidate_citation_count`. The `0.1·is_influential` term is
    **dropped — source-forced** (OpenAlex exposes no influential-citation count). Promote top ~200 each.
- *Query reformulation:* gpt-5.5 reformulates the boolean queries using the top judged-relevant
  papers as exemplars (port `_dense_reformulate_prompt_tmpl` adapted to boolean syntax; PF:
  `agents/.../dense/formulation_prompts.py`), retrieve again.

**Step 4 — Judge pass 2 (adaptive):** continue adaptive judging on new candidates until the
per-query budget (~250 judged) is reached **or** the **`HighlyRelevantShortcircuit`** fires —
≥1 Perfect found AND accumulated score ≥ 50 (+2/Perfect, +1/Somewhat) — identical to Arm C
(PF: `agents/.../dense/relevance_loading_optimization.py`). *(Replaces the old "no new Perfect
in the last 50 judgments" heuristic — incidental, removed.)*

**Step 5 — Final ranking (content blend + intent weights — identical to Arm C minus the snippet term):**
```
content = 0.9·judge_score + 0.075·cohere_rerank          (no snippet term — source-forced, see below)
score   = w_content × content
        + w_recent  × sigmoid(year − baseline_year)
        + w_central × sigmoid(log(cited_by_count + 1))
```
Cohere `rerank-english-v3.0` over (query, title+abstract), batched ≤500/req (PF:
`agents/.../external_api/rerank/cohere.py`); content blend `content_relevance_score()`
(PF: `agents/.../common/sorting.py`). Weights set per query from the Step-0 intent
(paper-finder `SortPreferences`):

| Query intent | w_content | w_recent | w_central |
|---|---|---|---|
| just topic (default) | 0.95 | 0.025 | 0.025 |
| recent X | 0.80 | 0.175 | 0.025 |
| influential X | 0.80 | 0.025 | 0.175 |
| recent + influential X | 0.80 | 0.10 | 0.10 |

Output a ranked list capped at **250 results** (ASTA-bench cap). Because recall@k_est
counts Perfect papers in the **top-k_est**, this blend can move relevant papers in or out
of the scored window — see §4.7 sensitivity analysis.

**Source-forced differences from Arm C (the only ones that remain).** Everything else —
adaptive judging, short-circuit, snowball structure, reformulation, Cohere reranker, intent
blend, budgets, models, judge — is **identical to Arm C**. The four genuine differences exist
only because OpenAlex cannot do what S2 does:
1. **No dense/snippet leg** (Step 1) — OpenAlex has no S2-style snippet/dense search API.
2. **No influential-citation term** in snowball scoring (Step 3).
3. **No snippet term** in the content blend (Step 5) — judge & cohere keep their PF weights and
   the final blend normalises components (PF `weighted_average_sort`), so the dropped `0.025`
   needs no re-normalisation.
4. **Abstracts via Crossref enrichment** (§4.4), not native S2.

### 4.3a Arm C — faithful Paper Finder agent (Semantic Scholar)

Now that the Semantic Scholar (S2) API is available, Arm C runs the **same** Paper Finder
machinery as Arm B (they are mechanism-identical, §4.3; PF:
`agents/.../complex_search/broad_search.py`) on the S2 corpus, **plus** the three capabilities
OpenAlex cannot provide:

1. **Hosted dense/snippet retrieval** (S2 `/snippet/search`) — Arm B has no dense leg; S2
   supplies it without our building an index. This also gives Arm C the `0.025·snippet` term
   in the content blend (PF: `agents/.../common/sorting.py`), which Arm B lacks.
2. **Forward citation expansion with an influential-citation signal** — S2 exposes
   `influentialCitationCount`; Arm B's snowball drops that term (OpenAlex has no influence
   signal). PF snowball scoring: `agents/.../snowball/snowball_agent.py:319–365`.
3. **Native abstract coverage** — S2 `abstract` / `tldr` / snippets, vs Arm B's Crossref
   enrichment (§4.4).

The agentic machinery — adaptive Thompson-sampling judging and the `HighlyRelevantShortcircuit`
(both PF: `agents/.../dense/relevance_loading_optimization.py`), the Cohere reranker (PF:
`agents/.../external_api/rerank/cohere.py`), and reformulation — is **shared with Arm B**, not
C-exclusive (§4.3).

Arm C reuses **Arm B's Step 0 query analysis verbatim** (content extraction +
recency/centrality intent, gpt-5.5) so query understanding is held constant across B and C.
It is scored by the **same frozen judge (§4.5)** and carries the same per-result `origins`
set (§4.3).

**Source of truth (PF).** Every Arm C mechanism below is a port from **PF**
(`asta-paper-finder`); exact files are tagged inline and listed in §3. Recall-defining metrics
follow **BENCH** (§4.7). Where this spec's numbers (budgets, top-k, model names) differ from
PF's config, **this spec wins** — PF is the algorithm, not the operating point.

**Scope — broad-by-description only.** Arm C ports PF's broad-search workflow (PF:
`agents/.../complex_search/broad_search.py`, `BroadSearchAgent`), **not** the upstream
query-analyzer *router* (PF: `agents/paper_finder/paper_finder_agent.py`) nor the
specific-by-title / by-name / by-author / metadata-only workflows. Policy Atlas's `retrieve`
is always *evidence gathering over a plan-derived query* (v3 brief §4: "retrieve — acquire new
external evidence"; the product's four intents — spending decision / scrutinise / scope options
/ find evidence — are all synthesis, never known-item lookup), so those routes would never
fire. We therefore keep only PF's **content + recency/centrality** extractions (§4.3 Step 0)
and drop its author / venue / title-match / broad-vs-specific extractions — fewer LLM calls,
no behaviour lost for our query distribution. Recency/centrality stays because it is ranking
*intent*, not a metadata route.

**Port note — don't copy the metadata filter.** PF's `broad_search.execute` ends with
`filter_docs_by_metadata(docs, time_range, venues)`. Because we remove the analyzer that
populates `time_range`/`venues`, invoke it with both unset (a no-op) — do **not** port a hard
metadata filter driven by an extractor we've deleted; it would silently drop candidates and
depress recall@k_est. Soft scoping (geography, study type) is folded into the query text per
§4.1, consistent with the v3 brief's "scoping = soft prior, not a hidden re-weight." If
known-item / metadata retrieval ever becomes a product need, PF's router is the reference to
revisit (§8).

> **B↔C now isolates the source.** With the machinery unified (§4.3), Arm C differs from Arm B
> only in the source-forced bundle — S2 corpus + dense leg + influential-citation signal +
> native abstracts. So **B→C is a clean single-axis step: "what S2 buys you."** The one residual
> is that those four ride together (arm design can't unbundle "S2 corpus" from "S2 dense");
> origin tags (§4.7) decompose them *within* Arm C — e.g. the dense-origin share of Arm C-only
> Perfect papers separates dense from corpus.

**Operating point:** diligent-equivalent — 2 iterations, ~250 judged candidates/query, dense
top-k 250/query, snowball forward/backward top-k 200. Cost logged, not capped (Arm C is the
most expensive arm; its cost/recall point is a headline finding). Fast-mode is out of scope (§8).

**Step 0 — query analysis (gpt-5.5):** identical to Arm B §4.3 Step 0 — reuse the cached
call results. Weighted relevance criteria still come from the judge (§4.5), not here.

**Step 1 — initial retrieval (parallel, S2):**
- *Dense/snippet search:* gpt-5.5 formulates N=5 diverse dense queries (port
  `_dense_formulation_prompt_multiple_tmpl`, PF: `agents/.../dense/formulation_prompts.py`);
  each → S2 `/snippet/search`, top-k 250.
  Retrieved snippets are stored on the candidate — this is what populates `num_snippets` for
  the Step-5 blend. **Coverage caveat (measured):** S2's full-text/snippet index is heaviest
  on open-access STEM (arXiv/ACL heritage); coverage of policy and grey literature is unknown
  for our query set. Log per-query snippet-hit rate and the dense leg's origin share — a weak
  dense leg on policy topics would handicap Arm C for *corpus* reasons orthogonal to the
  architecture (see §7).
- *Keyword/relevance search:* each query → S2 `/paper/search` (relevance-ranked), requesting
  `abstract, tldr, externalIds, citationCount, influentialCitationCount, year, publicationDate`.
- *LLM parametric suggestions:* gpt-5.5 names ~10–15 candidate papers; ground each against S2
  by title match (`/paper/search` `match_title`) ±2-year window and by DOI via `externalIds`;
  ungrounded suggestions dropped (as Arm B).

**Step 2 — judge pass 1 (adaptive):** dedupe by S2 `corpusId` (then DOI/`externalIds`; merge
`origins`). Abstracts come from S2 (`abstract` → `tldr` → snippet text; title-only flagged) —
the Crossref/Europe-PMC chain (§4.4) is **not** used by this arm. Then judge **adaptively**
rather than strictly by rank: port Paper Finder's `adaptive_load` (PF:
`agents/.../dense/relevance_loading_optimization.py`) — uniform-preload 5
candidates per origin, then **Batched Thompson Sampling** (`initial_batch_size=20`,
`batch_growth_factor=2`, `window_size=20`, `decay_factor=0.95`, ≤50 concurrent) steering the
per-iteration judging budget (~150) toward origins with higher observed relevance reward,
stopping when the budget is spent or the short-circuit fires.

**Step 3 — expansion (parallel):**
- *Citation snowballing* from seeds = papers judged ≥2:
  - forward: S2 `/paper/{id}/citations` (carries `influentialCitationCount`)
  - backward: S2 `/paper/{id}/references`
  - score (port `score_snowball_candidate`, PF: `agents/.../snowball/snowball_agent.py:319–365`): forward
    `1.0·seed_relevance + 0.1·is_influential − 0.005·candidate_citation_count`; backward
    `1.0·seed_relevance − 0.0005·candidate_citation_count` (no influential bias)
  - promote top ~200 each direction.
- *Query reformulation:* gpt-5.5 reformulates dense queries using the top judged-relevant
  papers as exemplars (port `_dense_reformulate_prompt_tmpl`, PF: same `formulation_prompts.py`); retrieve again via snippet +
  relevance search.

**Step 4 — judge pass 2 (adaptive):** continue adaptive judging on new candidates until the
per-query budget (~250 judged) is reached **or** the **`HighlyRelevantShortcircuit`** (PF:
`agents/.../dense/relevance_loading_optimization.py`) fires:
stop once ≥1 Perfect (3) paper has been found **and** accumulated score ≥ cap (50), scoring
+2 per Perfect and +1 per Somewhat (`highly_relevant_cap=50`). This is Paper Finder's actual
stopping rule, **identical to Arm B** (§4.3) — both arms share it so judged-set sizes are
comparable. **Record which condition fired** (budget vs short-circuit) for each query/arm.

**Step 5 — final ranking (full Paper Finder content blend, PF: `agents/.../common/sorting.py` `content_relevance_score()`; + intent weights):**
```
content = 0.9·judge_score + 0.075·cohere_rerank + 0.025·sigmoid(num_snippets)
score   = w_content × content
        + w_recent  × sigmoid(year − baseline_year)
        + w_central × sigmoid(log(cited_by_count + 1))
```
`w_*` from the Step-0 intent using the **same weight table as Arm B (§4.3 Step 5)**. Cohere
`rerank-english-v3.0` (PF: `agents/.../external_api/rerank/cohere.py`) scores (query, title+abstract/snippet text), batched ≤500 docs/request.
Output a ranked list capped at **250** (ASTA-bench cap).

> **The reranker.** Both Arm B and Arm C carry the Cohere term in their live blend — it is part
> of the unified machinery (§4.3; PF: `agents/.../external_api/rerank/cohere.py`). The §4.7
> sweep additionally re-scores each arm's already-judged pool with the Cohere (and, for C,
> snippet) term toggled on/off, giving the reranker's isolated marginal effect on nDCG/precision
> per arm (plus confirmation it is ≈inert for recall@k_est).

### 4.4 Abstract enrichment

**Scope: Arms A/B (OpenAlex) only.** Arm C sources abstracts natively from S2 (§4.3a) and
skips this chain entirely. For Arms A/B we deliberately keep the OpenAlex-native pipeline and
do **not** pull S2 abstracts — this keeps the baseline arms faithful to the v2/OpenAlex design
and confines S2 to Arm C, preserving the source boundary the comparison relies on. S2 would be
the highest-coverage abstract source, but folding it into A/B would blur that boundary. The
MVP therefore uses a single resolver, **Crossref by DOI**, and measures whether that is enough:

For any candidate without an abstract after PyAlex reinversion:
1. **Crossref** by DOI → abstract (`jats:abstract` where deposited).
2. Else: judge on title only, flagged `text_basis="title_only"`.

Caveat (drives the trigger below): OpenAlex already ingests abstracts *from* Crossref, so
papers missing an abstract in OpenAlex are disproportionately ones Crossref also lacks —
the marginal yield is expected to be modest, and DOI-less papers can't be looked up at all.

**Measured trigger.** The enrichment layer is a pluggable resolver chain. Log per-arm
**title-only fraction** and Crossref hit rate on the first real run. If the title-only
fraction is high enough to threaten the metrics (provisional bar: **>15%** of judged
candidates, or any arm-asymmetry that could bias the comparison), add **Europe PMC** by
DOI/title as a second resolver — free, keyless, with PubMed/PMC-sourced abstracts that are
*independent* of Crossref/OpenAlex and strongest in Nesta's health/social-policy domains.
(S2 access has returned but is intentionally confined to Arm C to keep the A/B source boundary clean; revisit only if the title-only fraction threatens the A/B comparison.)

Report metrics overall and excluding title-only papers (judge under-crediting check),
because an arm that surfaces more paywalled policy literature must not be silently punished
by the judge — with S2 gone, the title-only fraction is the metric to watch.

### 4.5 The relevance judge — frozen instrument

Direct port of ASTA's judging structure — follow **BENCH** `astabench/evals/paper_finder/relevance.py` (the definition the recall metric is built on; PF's `relevance.py` is equivalent).

**Per-query setup — criteria extraction (gpt-5.5, once per query, arm-independent).**
The judge first decomposes the query's free-text research question into weighted criteria
`{name, description, weight}` (port of `_relevance_criteria_prompt_tmpl`; BENCH `relevance.py`). This is a
function of the **query, not the retrieval method**, so the same criteria set is applied
identically to *every* arm's candidates — the v2 boolean baseline (Arm A), the OpenAlex
OpenAlex Paper Finder arm (Arm B), and the S2 Paper Finder arm (Arm C) are judged against the same criteria.
This is why the baseline needs no
criteria-producing step of its own: the judge brings the criteria to the papers. Criteria
are computed once per query, cached, and reused by the ensemble's reformulation loop, the
report, and the companion judge spec.

**Per-paper judging:**
- **Model:** gpt-5.4-mini, minimal reasoning, high concurrency (batched, ~50–75 parallel).
  *(Impl note, 2026-06-15: the backend `get_llm`/`LLMProcessor` path does not expose
  `reasoning_effort`, so "minimal reasoning" is not yet wired — the model name is set from
  `config.py`; reasoning-effort is a deferred knob, to add when the judge's cost/quality is
  tuned. Doesn't affect the parity-tested scoring.)*
- **Input per paper:** title + abstract (+ enrichment flag) + the query's weighted criteria.
- **Output per criterion:** `Perfectly Relevant | Somewhat Relevant | Not Relevant`,
  plus a verbatim supporting snippet (≤20 words) and a ≤30-word summary.
- **Scoring:** per-criterion 3.0/1.0/0.0 →
  `score = min(1.0, Σ weight_i × criterion_score_i / 3)` →
  bucket: `<0.25 → 0`, `<0.67 → 1`, `<0.99 → 2`, else `3` (BENCH: `calculate_relevance_criteria_score` + `calculate_0_to_3_relevance`, `relevance.py:248–274`).
- **Caching:** every judgment keyed by `(query_id, openalex_id)` and persisted
  (`judgements/` parquet) — papers pooled across arms and normalizer runs are judged
  exactly once. This is what makes the padded normalizer affordable and the run resumable.
  **The companion judge spec consumes this same cache**, so judging here is not redone there.

This judge is *used*, not *validated*, in this experiment. Its quality (vs v2's judge and
vs human labels) is the companion spec's subject.

**Prompt framing (impl note, 2026-06-15).** Both judge prompts carry a light
**policy-research domain framing** — an "expert research and policy analyst" persona and a
note that the question comes from an evidence-synthesis context — to improve the judge's
*construct validity* (proxying a Nesta policy researcher's notion of relevance). Because this
framing is query-independent and applied identically to every arm, it does not threaten the
cross-arm ranking validity (§1, §7). It deliberately does **not** import v2's
`RELEVANCE_SYSTEM_PROMPT` machinery: **no PICO/wizard slots** (population/outcome/geography
enter via the query text per §4.1, then the criteria-extraction step turns them into content
criteria), **no evidence-type preference** (study design is the strength-scoring layer's job,
§4.7 — a judge that rewarded RCTs/SRs would corrupt both recall and the evidence-mix metric),
and **no hard geography exclusion** (soft prior only, §4.3a). Criteria are content-only,
matching PF's `_identify_relevance_criteria_prompt_tmpl`.

### 4.6 Ground truth: padded pooled normalizer

Per query, the relevant-paper denominator is estimated ASTA-style:

1. **Pool** = union of judged results from: Arm A, Arm B, Arm C, **plus normalizer-only
   lenient runs** that never compete as arms:
   - a high-volume multi-query sweep (N=10 queries, max_results=500, lenient phrasing)
   - an extra parametric-suggestions run at higher temperature
   - an extra snowball hop from all Perfect papers (depth 2, backward only)
   - **an S2 lenient dense sweep** (now available): high-k snippet search over the N=10
     lenient formulations — a *source-independent* contributor that strengthens the
     denominator and partly offsets the judge-in-the-loop coupling risk (§7)
2. **k_est** = `ceil(count × factor)` where `count` = papers judged Perfect=3 in the pool
   and `factor = max(2, 2/ln(count))` for `count > 1`, else `factor = 10` (the cap only ever
   bites at `count = 1`). Reimplemented from `asta-bench/.../paper_finder_utils.py:154–196`,
   with unit tests asserting parity against these hand-computed values: count 1→**10**,
   2→**6**, 3→**6**, 5→**10**, 10→**20**, 100→**200** (note only count=2 clears the ×2 floor,
   at ×2.885).
3. Only **Perfect (3)** counts toward recall, exactly as ASTA-bench.

Note: the inflation factor caps achievable recall (e.g. ×2 → max recall 0.5), so headline
recall numbers look low by construction — the report states this in plain English so
"0.52" is read as "found 52% of an inflated estimate of the relevant set," not "missed half."

### 4.7 Metrics

Per query, per arm (over the ≤250-result ranked list):

| Metric | Role | Definition |
|---|---|---|
| **Recall@k_est** | **Headline** | Perfect papers in top-k_est ÷ k_est (BENCH: `calc_recall_at_k` `eval.py:117–153`; Perfect-only numerator via `count_relevant`) |
| Perfect-papers-found (raw count) | Headline companion | absolute count of Perfect papers in the arm's list — read alongside recall so the sparse-literature stratum (tiny counts → big inflation → low-looking recall) is interpretable |
| Corrected nDCG | Secondary | `(DCG − min_DCG)/(max_DCG − min_DCG)` over the judged multiset, rel ∈ {0..3} (BENCH: `lower_bound_corrected_ndcg` + `find_dcg` `eval.py:166–182`) |
| Precision | Secondary | **Perfect (=3) ÷ judged**, matching asta-bench exactly (BENCH: `calc_precision` `astabench/evals/paper_finder/eval.py:157–163`; relevance via `count_relevant` `:88–101`), at k ∈ {25, 50, 100, 250}. |
| Adjusted F1 | Secondary (ASTA comparability) | harmonic mean(recall@k_est, corrected nDCG) (BENCH: `calc_adjusted_f1` `eval.py:193`; harmonic mean `_calc_any_f` `:185–190`) |
| Evidence-mix recall | Secondary | recall stratified by a light evidence-category pass (SR/RCT/observational/other) over Perfect papers — ties "coverage" to what strength scoring needs |
| Ranking-weight sensitivity | Secondary | recall@k_est / nDCG recomputed under a small sweep of (content/recent/central) weight vectors **and** the Cohere-rerank (0.075) + snippet-count (0.025) content sub-terms toggled on/off, on the **already-judged pool** (cheap: re-rank only, no re-retrieval). Isolates the reranker's marginal effect **per arm** (Cohere for B & C; snippet term for C only). |
| **Cost** | Co-headline | per-arm per-query: LLM tokens by model (prompt/completion), OpenAlex+Crossref API calls, wall time |
| Origin attribution | Analysis | for each Perfect paper found by Arm B only / Arm C only: which mechanism(s) first surfaced it (dense, keyword, suggestions, fwd/bwd snowball, reformulation). For Arm C, the **dense-origin share of C-only Perfect papers** is what separates "S2 dense" from "S2 corpus" in the B→C step (§4.3a). |

Aggregate: mean per metric across queries, broken down by use case and literature
density; per-query win/loss table; a qualitative "papers only the ensemble found / only
baseline found" exhibit for the team session.

---

## 5. Harness & layout

```
backend/testing/r_and_d/search_experiments/
  pyproject.toml          # uv project; backend as editable path dep at ../../.. (v2 baseline, OpenAlexService reuse)
  README.md
  config.py               # frozen models, budgets, N values, blend-weight table — one dataclass, no config system
  queries/queries.jsonl
  query_analysis.py       # ensemble-side: content + recency/centrality intent (gpt-5.5)
  arms/
    baseline_v2.py        # run_baseline(query) — thin wrapper over backend services
    ensemble.py           # run_ensemble(query) — Arm B: full PF machinery on OpenAlex (§4.3)
    paper_finder_s2.py    # run_paper_finder_s2(query) — the §4.3a (Arm C) agent: S2 sources + adaptive judge + snowball + rerank
    normalizer_runs.py    # run_normalizer_pads(query) — incl. the S2 lenient dense sweep (§4.6)
  retrieval/
    openalex_client.py    # thin extension of backend OpenAlexService (cites:, referenced_works)
    s2_client.py          # Arm C: S2 relevance /paper/search, snippet /snippet/search, /citations, /references, /paper/batch
    dense_s2.py           # Arm C: dense-query formulation + reformulation prompts → snippet search; populates num_snippets
    enrich.py             # Arms A/B resolver chain: Crossref MVP (+ Europe PMC trigger). Arm C uses S2 natively, bypasses this.
    suggest.py            # parametric suggestions + grounding (OpenAlex for B, S2 for C)
    snowball.py           # OpenAlex (B, backward-only) + S2 (C, fwd w/ influential + bwd) scoring
  judge.py                # per-query criteria extraction (shared across arms) + criteria-based judge + persistent cache (consumed by companion judge spec too)
  adaptive.py             # Arms B & C: adaptive_load (Batched Thompson Sampling) + HighlyRelevantShortcircuit (PF: dense/relevance_loading_optimization.py)
  metrics.py              # recall@k_est, corrected nDCG, adjusted F1, inflation factor
  ranking.py              # Arms B & C: intent blend + Cohere rerank (PF: common/sorting.py, external_api/rerank/cohere.py); C adds snippet term; + weight/rerank sweep
  collect_results.py      # aggregate to per-arm/per-query tables (pandas)
  tests/                  # pytest unit tests (parity tests vs asta-bench formulas, judge pure logic)
    test_metrics.py       # parity tests (incl. inflation worked examples)
    test_judge.py         # judge schema/scoring/consolidation (offline)
  smoke/                  # one verbose end-to-end script per phase (live calls; prints each stage)
    _bootstrap.py         # sys.path + backend/.env setup, imported first by each smoke script
    phaseN_<name>.py      # e.g. phase1_metrics.py, phase2_judge.py
  results/                # parquet + per-run cost logs (incl. the shared judgments/ cache)
  report/findings.md
```

Conventions: REPL-first — modules expose objects and `run_xxx()` helpers; no `main()`,
no argparse, no `if __name__` blocks. Every retrieval and LLM call result cached to
disk so reruns are cheap and the experiment is resumable. All LLM calls log model +
prompt version. The `judgements/` cache and `queries.jsonl` are shared artefacts the
companion judge spec builds on.

---

## 6. Execution plan (~3 weeks, all three arms together, no human-annotation dependency)

All three arms ship as **one deliverable** — a single three-way comparison (the A→B→C ladder,
§4.3). Because B and C are mechanism-identical (§4.3), the **agentic core is built once**
(source-agnostic) and wired to two source clients; Arm A is a thin baseline wrapper. Build the
shared instruments + core first, then the three arms, then one metrics pass over all of them.

**Week 1 — instruments + shared core**
1. Query export + curation (~25 queries, stratified) — day 1–2
2. Judge instrument (BENCH `relevance.py`, §4.5) + retrieval metrics + parity tests (BENCH formulas, §3) + abstract enrichment — day 2–4
3. Shared **source-agnostic agentic core** (PF refs in §3): Step-0 query analysis, `adaptive_load` + `HighlyRelevantShortcircuit`, snowball scoring, reformulation, Cohere rerank, intent blend — day 4–5

**Week 2 — source clients + Arms A & B**
4. Source clients: OpenAlex (extend backend `OpenAlexService`: `cites:`, `referenced_works`) + S2 (`/paper/search`, `/snippet/search`, `/citations`, `/references`, `/paper/batch`) — day 6–7
5. Arm A (baseline) end-to-end through the frozen judge — day 7
6. Arm B = shared core wired to OpenAlex (no dense leg; `is_influential` term off; Crossref abstracts) — day 8–10

**Week 3 — Arm C + three-way evaluation**
7. Arm C = shared core wired to S2 + the S2-only pieces (reuses everything from step 3): dense/snippet leg + dense formulation/reformulation, `is_influential` snowball term, native abstracts — day 11–12
8. Normalizer padding runs (incl. the S2 lenient dense sweep, §4.6); full **three-way** metrics + reranker/snippet sweep — day 13–14
9. Findings report (A→B→C ladder, cost frontier, origin-attribution exhibits); team session — day 15

**Checkpoints**
- *After step 3 (core built):* dry-run judging cost/query against estimate (~600–900 judgments/query incl. normalizer pool); if far off, cut query count **now**, before wiring three arms to it.
- *After step 7 (S2 wired):* confirm S2 snippet coverage on the policy query set (§4.3a caveat); if the dense leg is near-empty on policy topics, de-scope dense and run Arm C as keyword + snowball only, recorded as a finding.

The only gating dependency is API throughput (no human-in-the-loop).

---

## 7. Risks & limitations (pre-registered)

- **Judge-defined ground truth:** recall is relative to the pooled-and-judged universe,
  not the true literature. **Arm rankings are robust** (same frozen judge scores both
  arms); **absolute numbers are not certified** until the companion judge spec validates
  the instrument against human labels — which also tests the one assumption that could
  break the ranking (judge errors correlated with which arm surfaced a paper).
- **Judge-in-the-loop coupling ("teaching to the test"):** Arm B uses the judge internally
  (gating snowball seeds / reformulation exemplars) while Arm A doesn't, so the ensemble
  partly optimises for the instrument that scores it. Fine *if* the judge tracks human
  relevance; a problem if it's biased. Until the companion spec's arm-correlated bias check
  passes, read a big ensemble win as "better at satisfying this judge," not yet "better at
  finding evidence." Partial mitigation: the normalizer (§4.6) includes non-judge-driven runs.
  **Arm C couples hardest of all** — its adaptive judging *allocates judging budget by judge
  reward*, on top of judge-gated snowball seeds and reformulation exemplars — so this caveat
  applies to Arm C most acutely. The new S2 lenient dense sweep in the normalizer pool (§4.6)
  is the main non-judge-driven counterweight.
- **Reduced enrichment without S2:** Crossref abstract deposition is patchy; expect more
  title-only papers than an S2-enabled run. Mitigation: Europe PMC seam, with/without
  title-only reporting, logged enrichment rates.
- **Intent-driven blend affects the headline:** recency/centrality reranking moves papers
  within the top-k_est window. The §4.7 weight sweep quantifies this so it's measured, not hidden.
- **Baseline handicap:** v2 runs without wizard PICO fields (v3-consistent but not
  production-identical). Optional sensitivity run noted in §4.2.
- **Parametric suggestions on policy topics:** likely weaker than on CS literature;
  origin attribution will show whether it earns its place.
- **OpenAlex rate limits:** forward-citation snowballing is request-heavy (one `cites:`
  call per seed). Polite pool + caching mitigate.
- **Semantic Scholar 1 req/s ceiling (cumulative across *all* endpoints):** the binding
  throughput constraint for Arm C — dense queries, per-seed forward `/citations`, and batch
  lookups all draw on the same 1/s budget, so Arm C is effectively serialized. Set the S2
  client **below** 1 req/s, cache every response, and expect Arm C wall-time to be dominated by
  this (factor it into the cost co-headline). Cohere trial-key limits are secondary (batch +
  cache mitigate).
- **Source coverage:** Arms A/B are OpenAlex-only and Arm C is S2-only; neither covers grey
  literature well, so all three may understate the real coverage gap (grey literature →
  Overton, phase 2).
- **B↔C source bundle (not a single atomic variable):** with the machinery unified (§4.3),
  B→C isolates the source — but the source-forced capabilities (S2 corpus + dense leg +
  influential-citation signal + native abstracts) ride *together*, so a B−C delta is "what S2
  buys you" as a bundle, not "S2 corpus alone." Mitigation: origin tags (§4.7) decompose it
  within Arm C — the dense-origin share separates dense from corpus. Far cleaner than before
  unification, but not atomic (§4.3a).
- **S2 dense corpus skew:** S2's full-text/snippet index is heaviest on open-access STEM
  (arXiv/ACL heritage). If coverage of policy/health/grey literature is thin, Arm C's dense
  leg underperforms for *corpus* reasons unrelated to the architecture. Mitigation: log
  snippet-hit rate + dense origin share; the step-7 checkpoint (§6) can de-scope dense to
  keyword + snowball if the index is near-empty on policy topics.
- **Cohere dependency:** Arm C's blend now has a hard third-party dependency (rate limits,
  cost, a vendor that could change the model). Cache all rerank scores keyed by
  `(query_id, corpus_id)` so reruns are free and the experiment stays resumable.
- **Arm C cost:** it is the most expensive arm by far (dense queries × iterations + adaptive
  judging + forward-citation snowball + rerank). The co-headline cost metric matters most
  here — a large recall win at 5–10× the cost is a different recommendation than a cheap one.

## 8. Out of scope

- **Relevance-judge quality** — the companion spec `spec_relevance_judge_experiment.md`
  (v2 vs ASTA vs human, Argilla annotation). Run after this experiment; reuses its pool.
- Overton (semantic multi-query, `min_similarity` sweep) — source layer kept swappable;
  judge and metrics already source-agnostic.
- **Owned/local** embedding index (Arm C uses S2's *hosted* dense search instead); a dense
  index over OpenAlex specifically; S2 as an enrichment source for Arms A/B (kept OpenAlex-native, §4.4).
- Specific-paper / metadata-only / author routing (Paper Finder has these; we run only broad-by-description).
- Production integration; fast-mode operating point for any arm (re-run the winner capped if it wins).

## 9. Prerequisites

- Production Postgres read access for the query export
- `OPENALEX_API_KEY` + `OPENALEX_EMAIL` (polite pool) — already in backend config
- Crossref polite-pool mailto (no key needed)
- OpenAI access to gpt-5.4-mini and gpt-5.5
- **Semantic Scholar API key** (Arm C — relevance/snippet/citations/references/batch). **Rate limit: 1 request/second cumulative across *all* endpoints** — set the client below 1 req/s (serialize + throttle) to avoid rejected requests; cache every call. Dominates Arm C wall-time (§7).
- **Cohere API key** (Arm B & C content blend + §4.7 rerank sweep). **Trial keys are free, rate-limited, and non-commercial** — fine for this research experiment; if throttling bites, batch ≤500 docs/req (already specced) and cache rerank scores by `(query_id, corpus_id)`.
