# Methodology — the A / B / C arms (slide companion)

A speaker-notes deck for presenting the retrieval experiment to DS colleagues. Each section = **one
slide**: bullets are what goes *on* the slide; "Why it matters" is what you *say*. Grounded in the
code under `backend/testing/r_and_d/search_experiments/` so claims are defensible in Q&A.

---

## Slide 1 — The question & the design

**On the slide**
- We compare three retrieval pipelines for finding policy-relevant academic papers, as a **ladder**:
  - **Arm A** = current production (single pass).
  - **Arm B** = A + an **agentic loop** (same source).
  - **Arm C** = B + a **different source** (Semantic Scholar instead of OpenAlex).
- Each rung adds **exactly one capability**, so a difference between rungs isolates that capability.
- The **only thing frozen across arms is the query text**; everything else (formulation, ranking) is
  *part of* the arm being measured.

**Why it matters (say this)**
- This is a controlled ablation, not a bake-off. A→B answers "does the agentic loop help?"; B→C answers
  "does the dense source help?". If we changed two things per rung we couldn't attribute the effect.
- The frozen input is the natural-language, PICO-folded research question (`queries/loader.py`:
  `query_text` is "the ONLY field fed to arms + judge"). Everything downstream is fair game because the
  ranker/formulation is what we're evaluating.

---

## Slide 2 — Arm A: the production baseline (single pass)

**On the slide** — `arms/arm_a.py`
- Formulate: **multi-query** boolean generation — `generate_boolean_queries_multi` (n=5), the *live*
  production setting (not the legacy single query).
- Expand: **SR/RCT fan-out** — each boolean → base / systematic-review / RCT variants.
- Search: OpenAlex, up to 200/variant, **citation floor** at production default (`DEFAULT_MIN_CITATIONS`).
- Rank: production's **native order** — OpenAlex lexical `relevance_score` desc, then variant priority.
- **No agentic loop, no relevance screen.** Judge the top **250** (`judge_quota`).

**Why it matters (say this)**
- Arm A is the "what users get today" floor. The headline "did we improve?" is measured against this.
- Key property: it's a **single shot** — formulate once, search, rank, stop. There's no feedback from
  what it found. That's the thing Arm B adds.
- Ranking is **lexical**, not learned/judged — OpenAlex's keyword-match score. Worth flagging because
  B and C rank very differently (next slides).

---

## Slide 3 — Arm B: the agentic loop (same source)

**On the slide** — `arms/arm_b.py` → shared `broad_search.py` over `OpenAlexSource`
- Same source (OpenAlex), same multi-query boolean formulation as A, same SR/RCT fan-out, same citation floor.
- **Adds the loop** (2 iterations): reformulate from what was found → snowball (follow citations/
  references) → parametric LLM suggestions → **adaptive judging** (judge incrementally, stop when enough).
- Ranks by a **source-agnostic blend**, not OpenAlex's lexical score:
  `0.9·judge + 0.075·cohere_rerank` (`ranking.py`).

**Why it matters (say this)**
- A→B is "single-pass vs iterative agent, holding source + formulation + citation floor constant." Any
  difference is *the loop*.
- Why a new ranker? Because B's candidate pool is **heterogeneous** — keyword hits + snowball + LLM
  suggestions — and only the keyword subset even *has* a lexical score. The blend ranks all origins on one
  scale (judge relevance + a reranker), which is also what lets B and C be ranked the *same* way.
- The citation floor is held at the production default across **all three arms** deliberately, so the
  ladder isn't confounded by "B/C also see low-citation papers A filtered out."

---

## Slide 4 — Arm C: swap the source to Semantic Scholar

**On the slide** — `arms/arm_c.py` (= Arm B with `S2Source` instead of `OpenAlexSource`)
- **Same loop, same judge, same blend** — only the source changes.
- S2's capabilities light up legs that were dormant in B (`source.py` `Capabilities`):
  - **dense search** (`/snippet/search`) — semantic, not just keyword.
  - **influential-citation** weighting in snowball.
  - a **snippet-count** term in the ranking blend.
  - **native abstracts** (no enrichment needed).

**Why it matters (say this)**
- B→C isolates **the source** (and the capabilities it unlocks). OpenAlex is keyword/boolean; S2 adds a
  *dense* (embedding-based) leg that finds papers by meaning, not term overlap.
- This is the most "AI-retrieval" arm. It's also the one our planned next step (Arm C′) extends — feeding
  the snippet *text* as evidence to the judge, not just counting snippets.
- Caveat to pre-empt: S2 is rate-limited (~1 req/s), so Arm C is slow to run — a cost, not a quality, issue.

---

## Slide 5 — The measuring instrument: one frozen judge + a pooled normalizer

**On the slide** — `judge.py`, `collect_results.py`, `metrics.py`
- **Judge** = an LLM scoring each paper 0–3 (Not / Somewhat / Highly / Perfect) against per-query
  relevance criteria. **Frozen and identical for every arm**; each paper judged **once** (shared cache).
- We have **no ground-truth list** of all relevant papers, so we build a **pooled normalizer**: union the
  judged papers across A∪B∪C; count the "Perfect" ones (`pool_perfect`); estimate the true relevant-set
  size as `k_est = ceil(pool_perfect × inflation_factor)`.
- Headline metric **`recall@k_est`** = Perfect papers an arm put in its top-`k_est` ÷ `k_est`.

**Why it matters (say this)**
- One judge applied identically is what makes arm scores comparable — we're measuring *retrieval*, not
  three different definitions of relevance.
- The pooled normalizer is a **silver standard, not gold**: the denominator is an *estimate* built from
  what our own arms found, inflated to leave room for papers none of them found. So `recall@k_est` is
  "fraction of an estimated relevant set," and is **capped at 1/factor (~0.5) by construction** — a "low"
  number means "found X% of an inflated estimate," not "missed half the literature." Say this explicitly
  or the absolute values will mislead the audience.
- Ported verbatim from AstaBench's PaperFinder benchmark (`metrics.py` parity-tested), so the method is
  externally anchored, not home-grown.

---

## Slide 6 — Plot 1: retrieved vs judged per query

**On the slide** — `plots.py:plot_retrieved_vs_judged`
- Per query: papers **retrieved** (open circle) vs **judged** (filled), one panel per arm; dashed line =
  the 250 judge budget.
- Arm B/C retrieve **thousands** (B up to ~4,900); judging is capped near 250.

**Why it matters (say this)**
- The gap shows the judge only ever sees a **small, variable slice** of each pool — for B's biggest
  queries, ~5%. So **recall rests heavily on the pre-judge *ranker*** getting relevant papers into the
  top-250 before the judge is even consulted. A ranking failure there is invisible in the judged metrics
  but caps recall.
- This is the single most important caveat for reading every other plot: judged ≠ retrieved, and the
  budget is the bottleneck, not the retrieval.

---

## Slide 7 — Plots 2–4: yield, recall@k_est, Perfects-found — at two relevance bars

**On the slide** — `plots.py` (Perfect set + `run_highly_relevant_plots`)
- Three distributions per arm (dots = queries, box = IQR/median, diamond = mean):
  - **Perfect-yield** = Perfects found ÷ papers judged (budget-normalised).
  - **recall@k_est** (the headline).
  - **Perfects found** (raw count).
- Each shown at two cutoffs: **Perfect only (level 3)** and **Highly Relevant and above (level ≥ 2)**.

**Why it matters (say this)**
- **Yield**, not raw Perfects, is the fair cross-arm comparison: arms judge *different numbers* of papers
  (A judges a full 250 off a huge pool; B/C stop early), so raw "Perfects found" is confounded by budget.
  Yield divides it out.
- The **Perfect vs Highly+** split is retrospective — same judged data, relaxed bar (no re-run). It
  matters because:
  - At **Perfect**, Arm B leads recall; at **Highly+**, **Arm C overtakes**. Arm C disproportionately
    surfaces "Highly relevant but not quite Perfect" papers — the dense source's signature.
  - A subtlety to own on the slide: **`recall@k_est` is a self-normalising ratio** — relaxing the bar
    grows the numerator (more papers count) *and* the denominator (`k_est` is derived from the pool at
    that bar). So an arm whose capture-rate is the same across tiers (Arm B) barely moves; an arm that's
    relatively better at the lower tier (Arm C) rises. **Arm B's flatness is the control that makes Arm
    C's rise meaningful** — it shows the lift is real, not a metric artefact.

---

## Slide 8 — What to take away

**On the slide**
- A→B = the loop; B→C = the dense source. One capability per rung.
- Compare arms on **yield** and **recall@k_est** (estimated, capped ~0.5), read against the **retrieved-
  vs-judged budget**.
- Arm C's edge shows up at the **Highly+** bar — motivating the next step (Arm C′: snippet *evidence* to
  the judge).

**Why it matters (say this)**
- The story isn't a single winner; it's "where does each capability pay off, and at what relevance bar."
- The budget-coverage and self-normalising-recall caveats aren't footnotes — they're how you avoid
  over-reading the absolute numbers.

---

### Appendix — code map (for the curious / Q&A)
| Concept | Where |
|---|---|
| Arm A (prod single-pass) | `arms/arm_a.py` |
| Arm B (loop, OpenAlex) | `arms/arm_b.py` → `broad_search.py`, `retrieval/openalex_client.py` |
| Arm C (loop, S2) | `arms/arm_c.py` → `retrieval/s2_client.py` |
| Capability flags (the 4 source diffs) | `source.py` `Capabilities` |
| Frozen judge + shared cache | `judge.py` |
| Pooled normalizer, recall@k_est, k_est, Perfect vs Highly | `collect_results.py`, `metrics.py` |
| Ranking blend (0.9·judge + 0.075·cohere [+ snippet]) | `ranking.py` |
| Plots | `plots.py` |
