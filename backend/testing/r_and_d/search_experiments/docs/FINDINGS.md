# Running findings log

Measure-first observations surfaced *during* the build phases (smoke runs, parity checks). This is
a working scratch log — the polished Phase 10 deliverable is `report/findings.md`, which will draw
from here. Newest first.

---

## 2026-06-30 — No fixed operator cap; heavy-boolean failure is load-dependent → mirror prod's per-variant skip

**Status:** resolved — added per-variant catch-and-skip to Arm A (`arm_a.py` retrieve) + Arm B
(`openalex_client.py` keyword_search), surfaced as `n_search_failures` on both results; added 502/504 to
the experiment retry forcelist (`config.openalex_retry_http_codes`). Follow-on to the 1 req/s gate below.

**Is there a "max servable boolean"? No — it's not an operator-count threshold.** Swept q02's real facet
groups, AND-ing one more in at a time (raw, 429-retried so rate doesn't pollute the 200-vs-500 signal):

| groups | operators | status | result count |
|---|---|---|---|
| 1–5 | 7 → 43 | 200 | 481k → 882 |
| 6 (+venue) | 51 | **504 timeout** (once) | — |
| 7 (+intervention) | 62 | 200 | 355 |

Non-monotonic: **43 ops OK, 51 ops failed, 62 ops OK** — adding a *narrowing* facet made the heavier query
*work*. And the level-6 504 was **transient**: re-fired 6× it returned 200 every time (count=464, 2–4s). So
the governing variable is **query execution cost** (term frequency × result cardinality), not operator
count — my earlier ES-clause-count guess was wrong. A static operator cap would be the wrong tool: it would
drop servable queries (the 62-op one) *and* still miss cost-timeouts on low-operator common-term queries.

**Production already handles this; the experiment had dropped it.** Prod fires all boolean variants via
`asyncio.gather(..., return_exceptions=True)` and skips any that error (`references.py:643-649`) — a failed
boolean is logged and skipped, surviving variants still contribute, all-fail → empty frame. Arm A *composes*
the prod pieces but re-implemented the search loop **without** that skip, so a single monster boolean (q01,
q02) crashed the whole query — an experiment artifact, not real prod behaviour. Arm B's loop had the same gap.

**Fix:** mirror prod's skip per boolean-variant in both OpenAlex arms (catch → log → continue, count into
`n_search_failures`); add 502/504 to the retry forcelist so transient gateway timeouts get ridden out *before*
a skip; and **revert the retry to prod's 3/0.5** (from the 06-26 6/1.0) — with the skip in place, the long
backoff is a redundant pre-skip band-aid that just wastes ~31s/doomed-variant and lets Arm A over-recover vs
the prod baseline. This is a **parity correction**, not a workaround — and it settles the q02 validity worry: keeping q02
with a skip is exactly what prod does, so no need to drop it like q01/q23. No operator cap added (wrong
abstraction + would diverge from prod). Residual cost: a truly-doomed variant still burns the full retry
budget (~31s) before being skipped — a pre-fire `_operator_count` guard could short-circuit that later, but
it's a latency optimisation, not correctness, and the sweep shows operator count is only a rough proxy.

---

## 2026-06-30 — OpenAlex now enforces an explicit >5-operator → 1 req/s governor (refines the two 06-26 entries)

**Status:** resolved — added a client-side 1 req/s gate that fires ONLY for heavy (>5-operator) queries
(`retrieval/_openalex_throttle.py`, installed from `_backend.get_openalex_service`). Production untouched.

A `run_latency.py` probe failed on q02 Arm B with `RetryError: too many 500 error responses`. Re-diagnosed
with the same raw-probe method as the entries below, firing q02's **exact** Arm B boolean (a 7-facet nested
AND — **71 boolean operators**) raw, 6×, from an idle network:

- It alternates **HTTP 500 ⇄ 429**, and the 429 body states the rule verbatim:
  > "Your query uses **71 boolean operators (OR/AND/NOT)**. Broad boolean searches are heavy for our search
  > cluster, so queries with **more than 5 operators are limited to 1 request per second per client**."
- A **2-group (≤5-operator) control** returns 200 in ~150ms from the same network/auth.
- A **newline-stripped** variant 500s identically → the embedded `%0A` is *not* the trigger.

**This refines, not contradicts, the "transient throttle" entry below.** That entry's probe fired q03 at
0.3s spacing (>3 req/s) and saw 200 6/6 — impossible under a 1-req/s governor — so the governor almost
certainly **postdates** it: OpenAlex has since introduced (or tightened) an explicit heavy-query limiter.
Consequences:
- The 06-26 retry ride-out (`max_retries=6`/`backoff=1.0`) was right for the burst-500s it targeted, but it
  **cannot** fix a >5-operator query — retrying within ~1s just re-trips the governor, producing the 500⇄429
  thrash (and burning the whole retry budget before `RetryError`). (Since reverted to prod's 3/0.5 — see the
  per-variant-skip entry above; the skip, not a long backoff, is the resilience now.)
- This also re-frames the q01/q23 drop (entry below): those are the *same* >5-operator overflow, not a
  separate "unparseable boolean" class.

**Fix:** a `threading`-based 1 req/s serialiser (sync twin of `s2_client._RateThrottle`) installed at the
single pyalex chokepoint `BaseOpenAlex._get_from_url`, gating **only** URLs whose OR/AND/NOT count exceeds 5.
Heavy-only is deliberate: snowball fires ~400 mostly-simple calls/query-iteration (≤5 operators, not
governed) — pacing *those* to 1 req/s would add ~7 min/iteration for nothing. `_operator_count` returns 71
for the q02 boolean (matches OpenAlex's own count) and 0 for snowball's id/cited_by/referenced_works calls.

**Follow-up (addressed in the per-variant-skip entry above):** at the time of writing this entry the monster
boolean still failed intermittently and "reduce Arm B's operator count" looked load-bearing. The later sweep
showed the failure is **transient/load-dependent, not a fixed complexity ceiling** (43 ops OK, 51 flaky, 62 OK),
and the q02 monster in fact *succeeds* once paced + retried (89 candidates). So the resolution was production
parity — per-variant catch-and-skip — not operator reduction; the gate + skip together carry it.

---

## 2026-06-28 — Arm C uses S2 snippets as a COUNT, not as evidence (vs PF) — bounds the B→C claim

**Status:** DOCUMENTED. The B→C ladder is still valid (same judge both arms); but Arm C is a *partial*
reproduction of PF's dense pipeline. A snippet-evidence variant (Arm C′) is a candidate next step the
user is interested in — design sketched at the end, not yet built.

**The question.** Does Arm C use S2 evidence snippets the way `asta-paper-finder` (PF) does? Compared
Arm C's S2 path against PF's snippet machinery end to end.

**Answer: no.** Arm C *retrieves* snippets via S2 `/snippet/search` but reduces them to (a) a **count**
and (b) a **single fallback abstract**. The snippet *text* almost never reaches the judge, and we use
none of PF's snippet-as-evidence machinery.

**What Arm C keeps (the shared spine — faithful):**
- Dense leg via `/snippet/search` (`retrieval/s2_client.py:283-289, 359-383`), ported from PF's dense
  formulation (`dense_s2.py`). See [[project_arm_c_keyword_leg_weak]] for the two-leg split.
- `num_snippets` as a saturating ranking term: `core/ranking.py:80-84` `num_snippets_score_sigmoid` is a
  direct port of PF's function; added as `+0.025·sigmoid(num_snippets)` only when `caps.has_snippets`
  (`core/ranking.py:195-196`, Arm-C-only — the §4.3 #3 source-forced diff).

**Where Arm C diverges from PF (all about snippet *text*, not retrieval):**
| Dimension | PF (`asta-paper-finder`) | Arm C |
|---|---|---|
| Snippets kept/paper | a **list**, section-grouped | **one** (first non-empty), or zero — `s2_client.py:154-155` |
| Sources | Vespa full-text dense (sections, offsets, `ref_mentions`) **+** citation contexts from *citing* papers (S2 `contexts`) — `dense.py:78-96`, `s2_rest.py:266` | S2 `/snippet/search` only; **no citation contexts** |
| Judge input | markdown = title + abstract[:1500] + **all snippets** + ≤20 **citation contexts** (`fields.py:13-54`) | `{title, abstract, text_basis}` only (`arm_b.py:73-81`, reused by Arm C) |
| Rerank text | Cohere over `title + join(snippets)` | Cohere over `title + abstract` only (`core/ranking.py:343-345`) |
| Verbatim evidence | LLM extracts `relevant_snippet`, then **fuzzy-matches back** to a real `Snippet`/`CitationContext` for provenance (`relevant_snippets.py:12-72`) | judge *emits* a snippet (`core/judge.py:144`) but from the abstract; never matched back |

**The single decisive line:** `s2_client.py:381` — `if not cand.abstract and info["snippet"]`. Snippet
text becomes the judged content **only when the paper has no abstract/tldr**. Once batch-hydration fills
a real abstract, the snippet is discarded. So in the common case, Arm C's snippets are **pure ranking
ballast** (they nudge order via `num_snippets`) and contribute **zero evidence** to the relevance
decision. PF inverts this: the snippet *is* the evidence — its judge reads abstract **and** body snippets
**and** citing-paper contexts, which is why PF can judge papers whose abstract alone wouldn't reveal the
match (the classic "method X buried in §4" case).

**Two verdicts (they point opposite ways):**
1. **B→C ladder remains valid.** Arm B and Arm C share the *same* abstract-only judge (`_make_judge_fn`
   reused verbatim, `arm_c.py:34-37`), so B→C cleanly isolates the dense source + its capability flags.
   Not contaminated. Consistent with the measure-first decision to judge on abstracts
   ([[project_phase4_measure_first]]).
2. **But Arm C is NOT a faithful reproduction of PF's dense pipeline.** It reproduces dense *retrieval*
   and the snippet *count* signal, not the snippet-as-evidence enrichment that is arguably PF's biggest
   judge-accuracy lever. Phase-10 report must not claim "Arm C ≈ a PaperFinder-style dense agent" without
   this caveat: PF feeds its judge section-level snippets + citation contexts that Arm C's judge never
   sees. Risk: Arm C may *retrieve* PF-quality candidates but then *judge* them with abstract-only myopia
   — exactly the body-relevant papers dense retrieval is best at surfacing — understating the source's value.

**Candidate next step — Arm C′ (snippet-evidence variant), NOT built:**
- Add `Candidate.snippets: list[str]` (the dataclass already accretes fields, `core/source.py:40-101`); have
  `_group_snippets` keep all snippet rows, not just the first (`s2_client.py:154-155`).
- Have the judge_fn concatenate abstract + snippets into the judged text (a snippet-aware variant of
  `arm_b._make_judge_fn`), and optionally rerank over snippet text too (`core/ranking.py:343-345`).
- Optionally attach citing-paper contexts in the forward snowball (PF `snippet_snowball.py:265-289`;
  ours carries `seed_relevance`/`is_influential` but no context text).
- This is the arm that actually answers "does snippet evidence lift judged recall?", and it doubles as
  the verbatim-evidence half of any future AstaBench submission (paper_id S2 CorpusID + `markdown_evidence`).
- Keep it a *separate* arm — C stays the clean B→C source comparison; C′ adds the evidence-enrichment axis.

**Evidence paths:** Arm C `retrieval/s2_client.py:141-155, 352-383`; ranking `core/ranking.py:80-84, 181-238,
343-345`; judge input `arms/arm_b.py:73-81` (reused by `arms/arm_c.py:34-37`). PF side:
`libs/dcollection/.../fetchers/dense.py:78-96`, `loaders/s2_rest.py:266`, `loaders/fields.py:13-54`,
`agents/mabool/.../computed_fields/relevance.py:51-71`, `.../relevant_snippets.py:12-72`,
`.../snippet_snowball.py:265-289`.

---

## 2026-06-26 — OpenAlex 500 was transient burst-throttle, NOT the query (corrects the entry below)

**Status:** resolved — hardened the OpenAlex retry experiment-side; the floor/drop below stand for their
*own* reasons (parity, realism) but were **not** what fixed the 500s.

The 500s kept happening *after* the floor went in (the failing URL has `cited_by_count:>5`), so the
"over-complex boolean" story below was **wrong**. Instrumented it raw (`requests`, no pyalex retry to
swallow the body):

- The **exact** failing q03 Arm B query → **HTTP 200, count=104, ~900ms** — 3 groups, 2 groups, 1 group,
  per-page 200 vs 25, all 200. Not complexity, not length, not pagination.
- The **real** `OpenAlexService.search` (api_key + floor) → 104 rows; **25-call burst → 0 failures**.
- Same query from the **user's own IP** (raw, with api_key) → **200, 6/6**. So the IP isn't hard-blocked
  and auth is fine.

→ The 500 is a **short transient throttle window**: Arm B's first `keyword_search` runs right after Arm A's
heavy q03 pagination (816 results → a burst), OpenAlex 500s the briefly-over-rate IP for a few-second
cooldown, and pyalex's prod retry (`max_retries=3, backoff=0.5` ≈ 3.5s of riding) exhausts *inside* that
window → `RetryError`. A manual probe seconds later sees 200 because the window cleared. Volume driver is
Arm B's snowball (`fetch_citations`+`fetch_references` per seed, ~400 req/query-iteration).

**Fix (experiment-side, production untouched):** harden the pyalex retry in `_backend.get_openalex_service`
to `CONFIG.openalex_max_retries=6` / `openalex_retry_backoff_factor=1.0` (≈31s ride-out, vs prod's ~3.5s).
pyalex `config` is a global read at request time, so this covers Arm B's snowball `Works` calls too;
`OpenAlexService.__init__` resets it to prod values, so it's re-applied after every construction. If 500s
persist, the next lever is a proactive ~6–7 req/s throttle (mirror the S2 `_RateThrottle`), not added yet
since the IP recovers on its own.

---

## 2026-06-26 — over-complex booleans 500 OpenAlex → floor all arms at 5 + drop 2 queries

**Status:** SUPERSEDED diagnosis (see entry above — the 500s were transient throttle, not query complexity).
The floor-all-arms + q01/q23 drop still stand, but for **parity + query realism**, not as the 500 fix.

The full run hit OpenAlex 500s (`RetryError: too many 500 error responses`). I *initially* read this as
several curated `query_text` being **over-folded** (every PICO facet + the full OECD country list woven in),
making the v2 generator emit a **7-way nested AND of huge OR-lists** (~5,000-char URL) too complex for
OpenAlex. **That was wrong** — the entry above proves the booleans return 200 fine; the 500s were transient
burst-throttle. (q01/q23 are still genuinely over-folded and unrealistic, so dropping them remains sound.)

**Two signals pinned it down:**
1. **Arm B failed far more than Arm A** (B: 0/3, A: 1/3 on the first three queries). The only systematic
   A-vs-B difference was the citation floor — A floored at `DEFAULT_MIN_CITATIONS` (5), B did not. The
   floor pre-narrows the corpus enough for OpenAlex to complete the query; without it, OpenAlex evaluates
   the monster boolean against everything and times out.
2. **q01 failed even *with* the floor** (Arm A, q01) — that one's boolean is too complex regardless.

**Fix:**
- **Floor all three arms at production's `DEFAULT_MIN_CITATIONS`** (was: A floored, B/C no-floor). This
  fixes the bulk of the 500s *and* removes a confound — the floor is now constant, so A→B isolates the
  loop and B→C isolates the source (flooring B *alone* would have confounded B→C: C would still retrieve
  <5-cite papers B excludes, masquerading as a dense-source advantage). Arm C (S2) gains a `min_citations`
  post-filter on its keyword+dense legs (strict `>`, matching OpenAlex's `cited_by_count:>n`); snowball/
  suggest stay unfloored on both B and C (mirrors `OpenAlexSource`, which floors only `keyword_search`).
  Cost: a 5-cite floor drops some recent/niche Perfect papers (the original no-floor rationale) — accepted
  because it's the production default and now *consistent* across arms.
- **Drop q01 + q23** (the two over-folded extremes) via `loader.EXCLUDED_QUERY_IDS`. `queries.jsonl` keeps
  them for provenance and all other `query_id`s stay stable (no renumber → no orphaned `results/`). The
  deeper lesson — the fold was too aggressive for a couple of multi-part questions — is noted for a future
  fold-conservatism pass; not re-folding the whole set now.

---

## 2026-06-26 — v2 boolean generator emits forbidden wildcards → OpenAlex 400

**Status:** worked around experiment-side (strip wildcards before search); a latent production gap.

The Phase-9 pilot's Arm A on q05 (water stress) hit `pyalex QueryError: Wildcards (* or ?) require the
exact (no-stem) field` — the generated boolean contained `agricultur*`. Root cause: the v2 boolean-gen
prompt (`app/services/analysis/prompts.py:33`) **explicitly forbids wildcards** ("DO NOT use wildcards
(*) … OpenAlex does not support them"), but **gpt-4.1 occasionally emits one anyway** — a model slip.

Production has **no defensive net**: `OpenAlexService.search` queries the *stemmed*
`title_and_abstract.search` field (which 400s on wildcards), and `sanitize_openalex_query` only strips
commas-in-quotes. So production's own search path would 400 on the same query — it relies entirely on
the prompt holding. (A real production robustness gap, surfaced by the experiment.)

**Fix (experiment-side, per decision — production left untouched):** a shared pure helper
`retrieval.openalex_client.strip_openalex_wildcards` removes `*`/`?` before search, applied in BOTH
OpenAlex arms (Arm A `arm_a.retrieve`, Arm B `openalex_client.keyword_search`). Dropping the wildcard
char leaves the stem (`agricultur`), which the stemmed field matches anyway — semantically equivalent,
not lossy. Arm C (S2) is unaffected (different engine; not OpenAlex's stemmed field). If production ever
wants the same robustness, the natural home is `sanitize_openalex_query`.

---

## 2026-06-26 — Arm C: S2 returns 429s despite the 1.1s throttle (cost, not a failure)

**Status:** NOTED — backoff absorbs it; consider nudging the throttle interval before the full run.

The Phase-8 smoke (q11, full loop) tripped **5 × HTTP 429** across `/paper/search`, `/citations`,
`/references` even though `_RateThrottle` serialises to `s2_min_request_interval_s = 1.1` (nominally
under S2's 1 req/s). `_raw_request`'s exponential backoff caught every one (`attempt 1/5; backing off
2.0s`) and retried successfully → exit 0, no lost data. So it's resilient, but each 429 adds a ≥2s
retry on top of the throttle, so **Arm C cold-run wall-time is worse than the nominal throttle implies**
(the §7 cost finding, amplified). Likely a stricter/bursty per-endpoint limit or shared-key pressure.
Cheap mitigation before `run_all`: bump `s2_min_request_interval_s` (e.g. 1.25–1.5) to trade a little
throughput for fewer backoff stalls. Not blocking — logged so the full-run cost is understood.

---

## 2026-06-26 — TECH-DEBT (revisit later): lazy in-function imports + scattered mkdir

**Status:** NOTED — user wants to refactor this holistically later (not now).

Two patterns the user flagged as not-loved, to clean up in a dedicated pass:

1. **Lazy `app.*` / sibling imports inside functions/closures/`__init__`** — e.g. `arm_a.ArmA.__init__`,
   `arm_b._make_judge_fn`/`run_query`, `openalex_client` methods, and the `from app.utils.llm.llm_utils
   import get_llm` in `core/judge.py`/`query_analysis.py`/`dense_s2.py`/`keyword_s2.py`/`fold_query.py`.
   *Rationale it grew this way:* keep modules import-clean so the pure mappers/helpers stay unit-testable
   with no backend env. *Concern:* it's scattered and obscures dependencies.
   Future options: a single backend-bootstrap seam, dependency injection of the app services, or a
   test conftest that makes top-level imports safe (then hoist imports to module top).

2. **`mkdir` side-effects inside functions** — `arm_a._persist` / `arm_b._persist` (results/arms/...),
   `ReferencesService.__init__` (export_dir), `judge.judge_papers` (RAW_DIR), `analyse_query` (ANALYSIS_DIR).
   *Concern:* directory creation is sprinkled across call sites. Future option: one results-tree bootstrap
   (ensure all dirs once at run start) instead of create-on-write in each function.

Not blocking the arms; logged so the refactor is deliberate and the rationale isn't lost.

---

## 2026-06-25 — Phase 7 Arm B: pending decisions (fanout + multi-query + ranker)

**Status:** DECIDED in principle (2026-06-25), to implement in Phase 7.

Surfaced while building Arm A. For the A→B rung to isolate *the agentic loop* (not bundle retrieval-feature
differences), Arm B should match Arm A's retrieval setup:
  - **Do the SR/RCT fanout in Arm B too** (user instinct). Otherwise B *loses* a retrieval feature A has,
    and A→B would conflate "the loop" with "lost the fanout." B currently (as planned) just searches the
    booleans — needs the same base/SR/RCT expansion.
  - **Set Arm B to multi-query** (consistent with Arm A = current-prod multi-query). B already calls
    `generate_boolean_queries_multi`, so this is mostly confirming n_runs/temperature parity with A.

**Ranking — DECIDED: Arm B/C keep the source-agnostic §4.3 blend; do NOT sort by OpenAlex
`relevance_score` + variant_priority.** Hard reasons:
  1. **B→C requires a source-agnostic ranker.** Arm C is Semantic Scholar — no OpenAlex `relevance_score`.
     B and C must rank by the same mechanism for B→C to isolate "the dense source"; the blend uses Cohere
     rerank (corpus-independent) precisely for this. `relevance_score` would break B→C.
  2. **B's pool is heterogeneous** (keyword + snowball + suggest); only the keyword subset has a
     `relevance_score`/`variant` at all. The blend (judge + Cohere + snippet + recency/centrality) ranks
     all origins uniformly. (B's Candidate objects don't even carry `relevance_score`.)
  3. A→B differing in ranker is fine — the ranker is part of each arm (only `query_text` is frozen): A =
     prod ranker (relevance+variant), B/C = new source-agnostic blend.
  **Evidence-type (SR/RCT) preference** is captured as the §4.7 "evidence-mix recall" *metric*, not folded
  into ranking — the cleaner home. Productising an SR/RCT ranking preference is a separate feature decision.

---

## 2026-06-25 — Arm A definition: current-prod multi-query baseline (deviates from spec §4.2)

**Status:** DECIDED (2026-06-25), to implement in Phase 6.

Spec §4.2 defines Arm A as a **single** boolean query at temperature=0. But current production defaults
to **multi-query** (`BOOLEAN_QUERY_GENERATION_MODE = "multi"`, `N_RUNS=5`, temp>0) — so the spec's
single-query Arm A is a *legacy* baseline, not what users get today.

**Decision:** Arm A = **current-production multi-query** (`generate_boolean_queries_multi`, n=5, prod
temperature), so the headline "vs baseline" measures improvement over the **live** system. Effects:
  - Tightens the ladder: A (live prod, multi-query, single pass) → B (+ agentic loop, same formulation)
    → C (+ dense S2 source). Each rung adds one capability; A→B no longer conflates multi-query+loop.
  - Multi-query's own value is already a shipped/known finding, so not re-measuring it as A→B is fine.
  - Cost: deviates from spec §4.2 (flag in the Phase 10 report); temp>0 is non-deterministic →
    **cache the formulation** per query (same as Arm B) for reproducibility.
  - Optional future A′ (single-query legacy floor) behind a flag — not building by default.

**Ordering:** Arm A reproduces production's native sort — `relevance_score` desc, then
`variant_priority` asc (SR > RCT > base on ties; `relevance_score` is OpenAlex's lexical score, NOT the
LLM judge). Requires carrying `relevance_score` + variant tag through the row mapping (the shared
`_df_to_rows` drops them). B/C rank by the §4.3 blend instead — correct, since the ranker is part of
each arm (only `query_text` is frozen across arms).

## 2026-06-25 — Dedup key: paper_id across all arms (not production's stable_doc_id content-hash)

**Status:** DECIDED for now (paper_id); revisit if DOI-duplicates distort recall.

Production's `build_references` dedupes on `stable_doc_id` (DOI → source_id → title+year hash) — a
**content hash that exists for cross-source merging** (OpenAlex↔Overton share DOIs, not source ids).
Our arms are OpenAlex-only, and the whole harness keys on `paper_id` (= OpenAlex work id): the shared
judge cache, cross-arm pooling, and every metric. So all arms dedup on `paper_id` for parity + simplicity.

**The caveat (why this is a finding, not a closed book):** DOI-first dedup is *more correct even
single-source* — it merges same-DOI OpenAlex duplicates (preprint + published listed as two work ids),
which `paper_id` keeps as two candidates and mildly double-counts in the pool. If we see DOI-dupes
materially affecting recall in Phases 6-9, the fix is a shared DOI-normalizing pre-dedup applied
uniformly to A/B/C (keeping `paper_id` as the surviving id). Not doing it now (YAGNI); logged so it's
not forgotten.

---

## 2026-06-23 — Arm C: S2 `/paper/search` returns 0 on long natural-language queries

**Status:** RESOLVED (2026-06-23) — root cause was a port-fidelity gap; fixed by mirroring PF's
two-agent formulation split. See "Resolution" at the end of this entry.

> **Update (2026-06-23): root cause found in the PF reference repo.** PF runs **two separate
> formulation passes for two separate endpoints** and never sends a dense NL query to the keyword
> endpoint:
> - dense leg: `DenseAgent` → `_dense_formulation_prompt_multiple_tmpl` → `/snippet/search` (verbose NL)
> - keyword leg: `BroadSearchByKeywordAgent` → **`_broad_search_prompt_tmpl`** → `/paper/search`
>   (a SHORT content-keyword query — the prompt strips descriptive words, forbids special syntax/hyphens)
>
> File: `asta-paper-finder/agents/mabool/api/mabool/agents/broad_search_by_keyword/broad_search_by_keyword_prompts.py:11`.
> We ported PF's dense formulation (`dense_s2.py`) but NOT its keyword formulation, then fed the dense
> queries to BOTH S2 legs. So we send `/paper/search` a query PF would only ever send to
> `/snippet/search`. The 0-results is OUR port gap, not intrinsic S2 behaviour.
>
> **PF-faithful fix:** add a keyword formulation for S2's `/paper/search` leg — a port of
> `_broad_search_prompt_tmpl` (keyword-stripper, plain text, no operators — S2 rejects boolean DSL on
> this endpoint). This also makes Arm C consistent with Arm B, which already gives its keyword leg its
> own formulation (v2 boolean generator, see [[project_arm_b_boolean_formulation]]); Arm C is currently
> the only arm reusing dense queries for keyword search. **Cost:** a second LLM formulation call —
> breaks the "single formulation feeds both legs" §4.3a simplification, but PF pays exactly that cost.
>
> This supersedes the "3 options" below: option 2 is now the PF-faithful default, in the specific form
> "port `_broad_search_prompt_tmpl` for the keyword leg only." Options 1/3 remain as fallbacks if the
> measured marginal recall doesn't justify the extra call.

**What we saw.** In `smoke/phase4_s2.py`, box 2 (`keyword_search`, limit 25) returned **0
candidates** for query 0, while box 3 (`dense_search`) returned 37 on the *same* query.

**Reproduction** (key-gated, but cheap — one cached call each):
```python
# from search_experiments dir
import asyncio, sys; sys.path.insert(0, ".")
import config  # noqa
from retrieval.s2_client import S2Source
src = S2Source()
asyncio.run(src.keyword_search("free school meals educational attainment", 25))          # -> 25 hits
asyncio.run(src.keyword_search(
    "impact of free school meal eligibility and provision on pupil achievement, "
    "test scores, and educational attainment in the United Kingdom", 25))                # -> 0 hits
asyncio.run(src.aclose())
```
Short, term-y query → 25 hits. Long dense-style sentence → 0. Confirmed it's **S2 endpoint
behaviour, not a parse bug** in `_paper_search` (the short query exercises the identical code path
and paginates fine).

**Why it matters.** `dense_s2.py`'s contract (and `broad_search`) feeds the **same dense NL
queries to BOTH** S2 legs: `/snippet/search` (dense) *and* `/paper/search` (relevance/keyword).
S2's relevance search is keyword-ish — it wants short term-y queries, not a dense sentence — so on
dense queries **Arm C's keyword leg is effectively dead**. Dense + snowball + suggest are carrying
all of Arm C's recall; the keyword leg is contributing ~nothing on these queries. This is a real
asymmetry vs Arm B, where the v2 *boolean* generator produces queries `/paper/search` is happy with.

**Decision deferred (do NOT silently rewire formulation).** Touches the deliberate §4.3a design
(single dense formulation feeds both legs) and the operating point. Options to weigh later:
  1. **Accept & document** — Arm C is the *dense* arm by design (§4.3 #1); a weak keyword leg is
     tolerable if dense/snowball/suggest hit recall targets. Cheapest, most faithful to the spec.
  2. **Dual formulation for S2** — also generate short keyword-ish queries for `/paper/search`
     (e.g. reuse v2's boolean/keyword generator for that leg only). Breaks the "one formulation,
     both legs" contract and adds an LLM call; muddies the clean B↔C divergence.
  3. **Drop the S2 keyword leg entirely** — if it never contributes, don't pay for it. Simplest,
     but loses any lexical-match recall the dense index misses.

**Recommendation (provisional):** lean (1) for the experiment as specced, and quantify the keyword
leg's *marginal* recall contribution in Arm C results — if it's ~0 across the curated query set,
that's itself the finding and argues for (3). Don't pre-empt with (2) before we have the numbers.

**Evidence path:** `smoke/phase4_s2.py` boxes 1–2 (now prints both query idioms side by side and
the keyword leg returning 25 candidates).

### Resolution (2026-06-23) — option (a): protocol-level two-leg formulation

Chose the architecturally faithful fix (PF runs two formulation agents, one per leg), implemented
through the existing `Capabilities` gate:

- **New `retrieval/keyword_s2.py`** — port of PF `_broad_search_prompt_tmpl` (pluralised to N diverse
  content-keyword queries): `formulate_keyword_queries` / `reformulate_keyword_queries`.
- **`SourceClient` protocol (core/source.py)** — renamed `formulate_queries`→`formulate_keyword_queries`
  and `reformulate`→`reformulate_keyword_queries` (explicit: these are the KEYWORD leg); added
  `formulate_dense_queries` / `reformulate_dense_queries` (DENSE leg, `caps.has_dense` only).
- **`core/broad_search.py`** — formulates each leg in its own idiom; `_retrieve_primary` iterates the
  keyword queries for `keyword_search` and the dense queries for `dense_search`. Dense formulation
  is only called when `caps.has_dense`, so Arm B is untouched.
- **`s2_client.py`** — keyword methods → `keyword_s2`, dense methods → `dense_s2`.
- **`openalex_client.py`** — keyword methods renamed; dense methods are `NotImplementedError` stubs
  (no dense leg; never called).

**Verified:** `smoke/phase4_s2.py` box 2 went 0 → 25 candidates; full offline suite green (137).
**Faithful extension noted:** PF emits ONE keyword query; we emit N diverse ones so the keyword leg
has the same per-query bandit arms the dense leg does (consistent with our N-diverse dense queries).
