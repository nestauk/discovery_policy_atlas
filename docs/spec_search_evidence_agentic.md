# Search Evidence: Agentic Spec

**Status:** Draft — in active spec discussion. Decisions below are confirmed during interview; open questions are flagged at the bottom.

This document captures the design for making `search_evidence` and its surrounding flow more agentic, in the MCP server. The frame is Claude Code's design pattern: small tools, transparency, soft gates, never re-traverse completed steps.

---

## Confirmed decisions

### 1. Self-correction: surface critique, propose fix

When `search_evidence` returns results that don't match the user's intent (e.g., the spike-finding example — UK obesity question returning predominantly US papers), the system should not silently retry. Instead, Claude reflects on the result quality and surfaces a critique with a proposed fix.

**Rejected alternatives:**
- *Silent auto-retry* — opaque; expensive on cascading failures; the user has no way to know the agent corrected itself
- *Quality flag per paper* — passive; doesn't propose an action
- *No reflection at all* — misses the spike's documented pain points (e.g., geography drift)

### 2. Pipeline architecture: many small tools, no formal gates

Following Claude Code's design pattern:

- Each step is a small, single-purpose tool
- The LLM chains tools autonomously based on conversation context
- No "may I proceed?" prompts between tools

Three soft-control mechanisms layered on top of the no-gates default:

1. **Pre-flight summary** — before starting a chain, Claude emits a one-sentence plan: *"I'll search the evidence, screen for UK relevance, and cluster by intervention — ~30s"*. The user has ~1s to interrupt before the chain runs.
2. **Plan widget** — if a chain has >4 steps, a dedicated widget renders an updating checklist. Inspired by Claude Code's `TaskCreate`/`TaskUpdate` surface.
3. **Host transparency + user interrupt** — every tool call is visible in Claude Desktop chat; user can interrupt by sending a new message.

**Rationale:** matches Claude Desktop UX expectations. Forces fewer modals; lets the user steer via the chat surface they already understand. Avoids the AutoGPT-style "trust the chain" failure mode by exposing every step.

### 3. Critique detection: LLM reflection

When critique runs, Claude reads the structured output and judges quality against the original question.

Deterministic heuristics (country counts, year skew, source mix) are computed alongside and **fed into** the LLM's reflection — but they don't make the judgement themselves. The LLM reasons over both the aggregate signal and the concrete papers.

**Rejected alternatives:**
- *Pure heuristics* — fast, but misses semantic drift that doesn't show up in metadata
- *Hybrid with heuristics making the call* — adds complexity for marginal gain over LLM-with-context
- *User-triggered only* — misses problems users don't notice

### 4. Critique input: top-N + wider compact set

For LLM reflection to be useful, it needs visibility beyond the top-5 papers shown to the user. Otherwise it can detect drift but cannot distinguish **search-bias** ("the search itself returned mostly US papers") from **rank-bias** ("the search was fine but ranking pushed US to the top").

`search_evidence` therefore returns two layers:

```python
class CompactPaper(BaseModel):
    """Trimmed paper representation for LLM reasoning over the wider result set."""
    doc_id: str
    rank: int                       # position in the full ranked set
    title: str
    abstract_snippet: str | None    # full abstract up to ~1800 chars; max signal for gap analysis
    year: int | None
    source_country: str | None
    venue: str | None
    document_type: str | None
    source: str | None              # 'openalex' or 'overton' (see §7 asymmetry)
    relevance_score: float | None   # from source API; may be 0 for Overton (see §7)
    query_variant: str | None       # which boolean query matched this paper
    variant_priority: int | None    # search strategy's priority for that query

class SearchEvidenceOutput(BaseModel):
    total_found: int
    results_returned: int
    results: list[EvidenceResult]          # top-N (default 5), rendered by widget
    additional_results: list[CompactPaper] # remaining ~45 in trimmed form, for LLM
    result_summary: ResultSummary | None   # aggregate stats; widget renders strip
    boolean_queries_used: list[str]
```

**Token cost:** ~20k tokens per call for `additional_results` (45 papers × ~450 tokens/paper at full-abstract snippets up to 1800 chars). Trivial in Claude Opus 4.7's 1M context — roughly 0.002% of the window.

**Why `abstract_snippet` is load-bearing:** title-only gap analysis is essentially keyword-matching. Abstract-augmented gap analysis lets the LLM identify *population subgroups, study design, outcomes measured, time horizon, intervention type* — exactly the dimensions that matter for "what's missing from this evidence base?" reflection (see §12). Including author conclusions (the last segment of an abstract) is also useful — the LLM can reason about *claimed* effect sizes and how the wider literature frames them, which informs gap analysis even when those framings need critique.

**Why the full abstract:** with a 1M context window, the constraint is information density, not size. 1800 chars captures essentially the complete abstract for almost all OpenAlex / Overton documents — intro, methods, results, discussion. Truncating earlier just discards signal for no real-world benefit.

**Asymmetry with the widget cards (intentional):** widget renders top-5 abstracts at 500 chars (enough for human glance — a long abstract on every card would crowd the UI). LLM reads `additional_results` at full-abstract length (it never needs to render them; it just reasons over them). One schema, two cuts of the same data, sized to each consumer.

**Key property:** the widget consumes `results`; the LLM also has access to `additional_results`. Different schemas serving different audiences via the same tool result.

### 5. Corrective action: surface from wider set first, re-search as fallback

When critique fires, the LLM's default behaviour:

- **If the wider set contains better candidates** → Claude surfaces them in chat with context: *"Goering 2011 at rank 11 is a Canadian Housing First RCT more relevant to UK context — want me to drill in?"* No new tool call.
- **If the wider set doesn't have better candidates** → Claude proposes re-calling `search_evidence` with adjusted args. User confirms; a second tool call happens. Original results stay in scroll-back for compare.

**No new tools needed.** The wider compact set is already in the LLM's context from the original `search_evidence` call.

This is the Claude-Code-style design: **transparency replaces formal gates**. The user sees the critique, sees the proposed fix, and can interrupt before the action by typing anything other than "yes."

### 6. Provenance: surface existing pipeline signals, no LLM rationale at search time

The `references.py` pipeline already computes three signals per paper that drive ranking:

| Field | Source | Type |
|---|---|---|
| `relevance_score` | OpenAlex API (BM25-ish text match score) | float |
| `query_variant` | Recorded at query-execution time | string label, e.g. `"broad"`, `"uk-stratified"` |
| `variant_priority` | Set at query generation time by the search strategy | int |

The final ranking is `sort_values(["relevance_score", "variant_priority"])` — these signals already drive the order, but `_row_to_evidence` in `tools.py` drops them at the MCP boundary.

**Decision:** plumb all three through to `EvidenceResult` (and `CompactPaper`). One-line addition to `_row_to_evidence`. The LLM critique can now reason about *why* the order is what it is, not just what the order is. Concretely, it can say *"top-5 all came from the broad query — papers from the uk-stratified query exist at rank 8+ but were tie-broken down by relevance_score; want to re-prioritise?"*.

**Rejected alternative — call `RelevanceService.check_relevance` inside `search_evidence`:**

The `RelevanceService` exists at `app/services/analysis/relevance.py` and *does* produce a `relevance_reason` (1-2 sentence LLM-written explanation) per paper. But this is structurally identical to the evidence categorisation we removed:

| | Evidence categorisation | LLM relevance check |
|---|---|---|
| Adds LLM call inside `search_evidence` | ✅ | ✅ |
| Latency ~5–15s for top-N | ✅ | ✅ |
| Runs on sparse metadata | ✅ | ✅ |
| Already runs in `run_analysis` | ✅ | ✅ |
| Risks rationalisation/wrong labels | ✅ | ✅ |

By the same logic that removed categorisation, LLM relevance assessment belongs at the *analysis* stage, not the *search* stage. Search returns candidates; analysis explains them.

### 7. Cross-source ranking asymmetry (known limitation, surface via critique)

The pipeline today has a latent ranking bug between OpenAlex and Overton:

- **OpenAlex papers** carry a numeric `relevance_score` from OpenAlex's API (BM25-ish text match score, typically 0.1–0.8).
- **Overton policy documents** *would* have a semantic-similarity score available from the Overton API (which uses `squery` + `min_similarity: 0.3`), but the score is **dropped at the `OvertonService.search` boundary** — only metadata is extracted.
- In `references.py:756-757`, missing `relevance_score` defaults to `0`. Every Overton document therefore carries `relevance_score = 0` into the merged DataFrame.
- The final ranking is `sort_values(["relevance_score", "variant_priority"])`. Overton documents are systematically deprioritised in the merged top-N — not because they're less relevant, but because they're unscored.

**Decision (Option A):** for this spec, *acknowledge the asymmetry rather than fix the ranking*. The fix touches multiple subsystems (Overton extraction, score normalisation across BM25 vs cosine-similarity metrics) and deserves its own design pass. Address the user-visible symptom through the agent's critique flow instead.

Concretely:

1. **Plumb `source` through `EvidenceResult` and `CompactPaper`** so the LLM can see at a glance which docs came from where.
2. **Have the LLM critique watch for source-mix skew.** When fewer policy documents than expected appear in the top-N — *and* the user's question is policy-relevant — the critique surfaces this as a candidate problem:
   > *"Top-5 are all academic papers; only 1 policy document despite querying both sources. This may reflect a known scoring asymmetry. Want me to re-run with source=overton only?"*
3. **Document the asymmetry in code** (`references.py` and `overton.py`) so future maintainers and the LLM (via tool docstring) know it exists.

**Rejected alternatives:**
- *Option B (extract Overton's similarity score):* OpenAlex BM25 and Overton cosine similarity aren't directly comparable. Normalising both into a unified score is a meaningful design decision in its own right.
- *Option C (rank separately, interleave):* Changes the result-list shape and the meaning of `total_found` / `max_results`. Worth doing, but bigger surface area than this spec should take on.

**Future spec:** "Cross-source ranking unification" — proper fix, tracked separately.

### 8. Result viz: aggregate summary strip, not charts

The widget renders results as a list of cards (already does). The only addition is a single-line **aggregate summary strip** above the cards, showing the composition of *the wider 50*, not just the top-5:

```
Evidence results
Found 50 papers · showing top 5
60% US · 20% UK · 20% other · 1998–2024 (median 2011) · 42 academic / 8 policy
```

Computed deterministically from the wider compact set (pandas `value_counts` on country / source / year). The widget reads it from a new `result_summary` field on `SearchEvidenceOutput`.

**Country-name normalisation** is applied inline during summary computation. OpenAlex's `source_country` is produced by `convert_country_codes_to_names` (full names like "United States"); Overton uses raw labels (often "USA", "UK", or ISO codes). Without normalisation the same country surfaces as two entries in the summary strip — observed in the wild as `"24% USA · 20% United States · …"`. Policy: hybrid — a small deterministic alias dict catches the predictable cross-source mismatches (US/UK and ~15 common others); novel weirdness in stats is caught by the LLM's gap-analysis reflection on the post-call surface (no extra LLM call needed for normalisation itself).

**Rejected alternatives:**

- *Timeline (year-vs-citation scatter)* — citation count is age-confounded; old papers always dominate, the chart screams "look how this paper is cited" rather than "is this evidence current?"
- *Geographic map* — needs a map library (~50–100 KB inlined) for what "60% US, 20% UK" already says faster
- *Cluster scatter (themes)* — needs embeddings + dim reduction; the LLM already describes themes in chat for free from the wider compact set
- *Multiple viz tabs* — turns the widget into its own app rather than a chat-embedded helper; overkill for top-5 + ~50

**Why text wins at this scale:**

The user's triage decision after a search is *"use these top-5, or refine?"* — and that decision is about the *retrieval*, not the *ranking*. A summary strip describing the wider 50 puts the decision-relevant info inside a single text line: zero interpretation step (`60% US` maps directly to a decision; a bar chart requires reading the axis, parsing the bars, translating to a number).

Charts would earn their place at a different scale (compare 3 searches, explore 200+ papers, interactive brush-to-filter). At top-5 + ~50, text wins.

The summary strip is **dual-purpose**: the widget renders it; the LLM also sees it in context and uses it for critique reasoning. Same data, two audiences — same pattern as the wider compact set itself.

### 9. Tool surface: three workflow-stage tools, no per-operation tools

The agentic surface has **three** MCP tools, each representing a *workflow stage*:

| Tool | Stage | What it does |
|---|---|---|
| `suggest_pico_options(question)` | Framing | Generates LLM-suggested PICO option sets for triage |
| `search_evidence(question, picks, …)` | Retrieval / triage | Hits OpenAlex/Overton; returns top-N + wider compact set + summary strip |
| `run_analysis(...)` | Deep analysis | Picks up from search_evidence's output; screens, extracts findings, synthesises across papers (NEW: see #10) |

That's it. No per-operation tools (`screen_results`, `cluster_results`, `compare_papers`, `expand_paper` etc.). The principle:

> **Tools represent distinct workflow stages with distinct external interactions, not distinct cognitive operations.**

Cognitive operations (compare, theme, drill into ranking, describe distributions) happen in chat via LLM reasoning over the wider compact set that `search_evidence` already returns. Only when the next operation needs **substantially different external interactions or compute** (deep extraction, full-text fetch, synthesis across many papers) does it become its own tool.

This works *because* of decision #4 (wider compact set). By pre-loading ~50 papers' metadata into LLM context per search, every subsequent reasoning operation between stages becomes chat-work — no second tool call needed.

**Rejected candidates and why:**

| Candidate | Why rejected |
|---|---|
| `screen_results(doc_ids, criteria)` | Most criteria (geography, source, year) are encodable as `search_evidence` args. Re-call covers it. Subtle criteria become chat work over the wider set. |
| `cluster_results(doc_ids)` | LLM can describe themes over the wider compact set in chat. No widget needed unless rendering as a viz. |
| `compare_papers(doc_ids)` | LLM has the top-5 abstracts already; comparison is chat work. |
| `expand_paper(doc_id)` | Full-text drill-in belongs to `run_analysis`, not search. From search, users go external (Open ↗ link) to read. |

### 10. `run_analysis` becomes a third MCP tool (data handoff from `search_evidence`)

`run_analysis` is currently a REST endpoint at `POST /{project_id}/run-analysis` (`backend/app/api/projects.py:815`) — project-tied, auth-gated, takes `query + search_context` and runs its own search before screening/extracting/synthesising. The current setup duplicates retrieval work that `search_evidence` already did.

**Decision:** make `run_analysis` an MCP tool that accepts the handoff payload from `search_evidence`, so retrieval is done once and the deep-analysis stage picks up where triage left off.

This deliberately crosses the "minimal tool surface" line — and is the right call here because `run_analysis` represents a **distinct workflow stage**, not a cognitive operation that the LLM could do in chat. It involves heavy work (screening 50–200 docs, extracting structured findings, synthesising across the set) that no amount of LLM-chat reasoning replicates.

End-to-end agent flow becomes:

```
User: "What works for reducing obesity in UK cities?"
Claude: [calls suggest_pico_options]           ← picker widget
User: [submits picks via picker]
Claude: "I'll search, then if results look strong I'll run full analysis (~5 min total)."
Claude: [calls search_evidence]                 ← results widget + summary strip
Claude: [critiques in chat: results look good, no source-mix issue]
Claude: [calls run_analysis with the handoff payload from search_evidence]
Claude: "Here's the synthesis…"
```

Soft control points still apply: pre-flight summary before the chain, host transparency on each tool call, user can interrupt by typing.

**Deferred decisions** (next implementation pass, not this spec):

- *Handoff payload shape* — what `search_evidence` returns that `run_analysis` consumes. Candidates: `doc_ids` only, full wider compact set, a cached references-CSV path, or a `search_id` that resolves to server-side state. Each has different state-management implications.
- *REST vs MCP coexistence* — does the existing REST endpoint stay (for the Policy Atlas app UI) and the MCP tool wrap it, or does the MCP tool replace it? Implementation detail; cleanest is probably "MCP tool wraps the REST endpoint, both stay alive."
- *Auth / project_id handling in MCP context* — current REST endpoint requires `current_user` and an existing project. MCP needs an answer for whether analysis runs ephemerally or always against a project, and how auth is presented.

These are real design problems but they're scoped to the analysis-integration spec, not this one.

---

### 12. Tool docstrings are agent instructions, not documentation

Per spike finding #7, MCP tool docstrings are not internal documentation — they're **load-bearing agent instructions** the LLM reads verbatim and treats as policy. Every word matters; vague guidance produces vague behaviour.

Each tool's docstring must cover **five sections**, in this order:

1. **When to call** — the precondition the LLM should verify before invoking
2. **What it returns** — schema-level summary, not implementation detail
3. **Presentation guidance** — how to present results to the user (terseness, format, what to omit)
4. **Post-call behaviour** — what reflection or follow-up is expected (critique, summary strip use, gating before next step)
5. **Hard constraints** — explicit "do not" clauses; concrete exclusions beat vague "be concise"

#### Concrete docstring contract per tool

**`suggest_pico_options(question: str)`**

```text
WHEN: Call this FIRST when scoping an unfamiliar research question, before
search_evidence. Skip if the user has already given explicit framings.

RETURNS: 3–5 options per facet (population, outcome, inner_setting). The picker
widget renders these for the user to select from.

PRESENTATION: After the tool returns, the widget will render the options. Do
not narrate the options as a markdown list — the widget shows them.

You MAY add a brief (1–2 sentence) critique if you notice something genuinely
useful: e.g. two or more options collapse to the same framing, a clearly-
relevant dimension is missing, or the question's terms are ambiguous and
produced shallow options. Keep critique terse — one sentence, no enumeration
of the options themselves. If options look clean, just say so briefly.

POST-CALL: Wait for the user's picks (delivered via app.sendMessage from the
picker). Do not call search_evidence without explicit user-confirmed picks.

DO NOT:
- Autonomously make picks for the user
- Re-call this tool to "refine" picks; users refine via the picker's custom inputs
- Proceed to search_evidence speculatively
- Critique at length; the picker is the selection surface, your critique is
  just a brief steer
```

**`search_evidence(question, population, outcome, inner_setting, geography, ...)`**

```text
WHEN: Call after the user has confirmed PICO picks (via the picker widget). May
also be called standalone if the user gives explicit search terms without going
through the picker.

RETURNS:
- results: top-5 papers (rendered by the search-evidence widget)
- additional_results: wider compact set of ~45 more papers (metadata only, for
  YOUR reasoning — not shown to the user)
- result_summary: aggregate stats over the wider 50 (rendered above the results
  by the widget; also available to you)
- boolean_queries_used: query variants run (auditability)
- (each paper carries: relevance_score, query_variant, variant_priority, source)

PRESENTATION: The widget renders top-5 + summary strip. Do not re-narrate
either. A single brief acknowledgement is enough ("Results above; ~30s search").

POST-CALL REFLECTION — REQUIRED:
After results return, silently perform a research gap analysis against the
user's question. Use result_summary (aggregate stats over the wider 50) +
additional_results (compact metadata of the wider set) to ground this in
actual data — don't speculate beyond what the results show.

Identify dimensions where the evidence base is THIN or MISSING relative to
what would fully answer the user's question:
  - Study designs (e.g. effectiveness question but no RCTs/quasi-experimental
    work in the set)
  - Populations or subgroups the question implies but results don't cover
  - Intervention types or delivery contexts that are conspicuously absent
  - Time periods (e.g. all pre-2015 when the question is about current
    practice)
  - Outcomes measured (e.g. question asks about long-term effects, results
    only report short-term)
  - Geographies, *as one dimension among many* — not the primary lens
  - Source-mix asymmetry as a known limitation (see §7): if the question is
    policy-relevant and few Overton docs surfaced, that may reflect ranking
    bias against policy documents, not a true literature gap

Then propose corrective actions grounded in the gap analysis:
  - For gaps that adjusted search args would address → propose re-calling
    search_evidence with the relevant change ("no RCTs in the top-50 — want
    me to retry with stricter study-design filtering?")
  - For gaps the wider set already partly addresses → name the specific
    buried papers ("Aubry 2020 at rank 12 covers the UK setting your
    question implied — want to look at it?")
  - For genuine evidence gaps (the literature simply doesn't exist in the
    indexed set) → note honestly ("no RCTs on this question appear in the
    indexed set — only observational evidence is available; the synthesis
    stage can still proceed on that, but flag the limitation")

Wait for explicit user confirmation before any corrective re-call. Surface
gaps even if no corrective action is possible — the user benefits from
knowing what's not in the evidence base.

DO NOT:
- Narrate the JSON; the widget renders it
- Auto-retry without user confirmation
- Treat the per-paper relevance_score as semantic relevance — it's a raw
  BM25-ish score, not an explained judgement
- Propose drilling into a paper's full text — that belongs to run_analysis
```

**`run_analysis(handoff_payload)`** — *contract sketched; exact signature pending §10 decisions*

```text
WHEN: Call ONLY after search_evidence has returned and the user has explicitly
confirmed they want deep analysis. Never auto-chain from search_evidence.

RETURNS: Synthesised findings across the analysed papers (schema TBD per the
analysis-integration spec).

PRESENTATION: Pre-flight summary REQUIRED before invoking, because this is
heavy (~5 min). Say what you'll do, give an ETA, allow user interrupt:
  "I'll run full analysis on these N papers — extracting findings and
   synthesising across them. ~5 min. OK to proceed?"
Wait for explicit "yes" or equivalent before calling.

POST-CALL: Walk the user through findings concisely; full report is in the
analysis widget. Don't re-narrate the whole report.

DO NOT:
- Auto-chain from search_evidence without explicit user signal
- Re-do the retrieval — use the handoff payload from search_evidence
- Run on uncritiqued search results (if critique flagged issues, address them
  before escalating to analysis)
```

#### Why this matters

From the spike findings: *"docstrings are load-bearing agent instructions, not internal docs. Every word in `suggest_pico_options`'s docstring was visible in Claude's responses."* The agentic behaviour designed in §§1–11 only manifests if the docstrings *say* so. Reflection won't happen unless we instruct it; critique won't propose corrective action unless we specify the action shape; the wider compact set won't be used unless we tell the LLM what it's for.

The docstrings are the spec **made executable**. They live in `app/mcp/tools.py` and ship with every `tools/list` response — they are quite literally what the LLM sees and reasons over.

### 11. Cross-session state: LLM context is the memory

No server-side session cache, no `search_id` token system, no project-tied persistence at the search stage. The wider compact set from each `search_evidence` call lives in Claude's conversation context naturally; that's the memory.

**Implications:**

- *Cheap and free.* No state to manage; no cache invalidation; no auth tied to session state.
- *Lossy by design.* Context can drift, old searches may eventually fall out of the LLM's effective context window over a long conversation.
- *The LLM can naturally reference earlier searches* in the same conversation ("this paper also appeared in your earlier search of X").
- *Project-tied persistence happens at the `run_analysis` stage*, not search. Search is ephemeral by design.

**Rejected alternatives:**

| Candidate | Why rejected |
|---|---|
| No state at all | Loses the natural cross-search reasoning the LLM can do in chat |
| Server-side session cache keyed by `search_id` | Adds state management for a benefit (cross-search compare) that the LLM already does for free via its context |
| Persistent project-tied state | Mixes search-stage (ephemeral) and analysis-stage (persistent) concerns. Search stays light. |

---

## Implementation checklist

Concrete code changes needed to realise the spec. Listed by file in dependency order.

### 1. Schema (`backend/app/mcp/schemas.py`)

- [ ] Add `ResultSummary` model with fields: `country_distribution: dict[str, int]`, `year_range: tuple[int, int]`, `year_median: int | None`, `source_mix: dict[str, int]`, `document_type_mix: dict[str, int]`, `open_access_fraction: float | None`
- [ ] Add `CompactPaper` model per §4 schema (10 fields including 1000-char `abstract_snippet`)
- [ ] Extend `EvidenceResult` with three new optional fields: `relevance_score: float | None`, `query_variant: str | None`, `variant_priority: int | None`
- [ ] Extend `SearchEvidenceOutput` with `additional_results: list[CompactPaper]` and `result_summary: ResultSummary | None`

### 2. Tool implementation (`backend/app/mcp/tools.py`)

- [ ] Extend `_row_to_evidence()` to extract the three new EvidenceResult fields (`relevance_score`, `query_variant`, `variant_priority`)
- [ ] Add helper `_row_to_compact_paper(row, rank)` that builds a `CompactPaper` with the 1000-char abstract snippet
- [ ] Add helper `_compute_result_summary(df)` that runs pandas `value_counts` over the full fetched DataFrame for country / source / document_type / year and computes OA fraction
- [ ] Update `search_evidence()` to:
  - Build `additional_results` from `df.iloc[max_results:]` (papers ranked 6+ in the wider 50)
  - Build `result_summary` from the *full* fetched DataFrame (not just the top-N)
  - Return all three layers (`results`, `additional_results`, `result_summary`)
- [ ] **Rewrite `suggest_pico_options` docstring** per §12 contract (when-call, returns, presentation, post-call, do-not)
- [ ] **Rewrite `search_evidence` docstring** per §12 contract — this is the substantive one; the gap-analysis post-call block is the load-bearing part

### 3. Widget (`backend/app/mcp/widgets/src/search-evidence.ts`)

- [ ] Add `ResultSummary` TypeScript type mirroring the Pydantic shape
- [ ] Add `renderSummaryStrip(summary)` function that produces the one-line aggregate strip (per §8 format)
- [ ] Call it above the `<ol class="results">` block in `renderResults()`
- [ ] Update the loading-state HTML to also have a placeholder for where the strip will appear (avoids layout jump on results arrival)

### 4. Widget CSS (`backend/app/mcp/widgets/src/search-evidence.css`)

- [ ] Add `.summary-strip` rule: muted text colour, smaller font, sits below the `Found N papers · showing top M` line, above `.results`

### 5. Build & smoke test

- [ ] `npm run build` in `backend/app/mcp/widgets/` — confirm both `pico-picker.html` and `search-evidence.html` rebuild cleanly
- [ ] `uv run python -c "from app.mcp import tools; from app.mcp.schemas import CompactPaper, ResultSummary, SearchEvidenceOutput; print('schema ok')"` — confirm imports
- [ ] Restart MCP server and run an end-to-end search; verify:
  - Widget renders with the summary strip
  - `additional_results` appears in the tool result `structuredContent` (inspect via MCP inspector or stderr logs)
  - LLM's response includes reflection / gap analysis without prompting

### 6. Deferred (next spec, do not implement here)

- `run_analysis` MCP tool wiring (decision §10 — needs handoff payload + auth design)
- Cross-source ranking unification (decision §7 — separate spec for BM25/cosine normalization)
- Error handling specifics (0-result searches, API timeouts)
- Telemetry / metrics

### Effort estimate

| Section | Lines of code | Risk |
|---|---|---|
| Schema additions | ~30 | Low — pure data classes |
| Tool wiring (3 helpers + search_evidence update) | ~80 | Low — read existing columns into existing patterns |
| Docstring rewrites | ~120 (across two tools) | Medium — these *are* the agentic behaviour; subtle wording matters |
| Widget + CSS | ~60 | Low — incremental on existing widget |
| **Total** | **~290 lines** | **Mostly low** |

The docstrings are the highest-leverage and highest-risk part. Everything else is mechanical plumbing.

---

## Out of scope for this spec

These dimensions came up during interview but were explicitly deferred:

- **Plan widget design** — only worth building if chains grow past ~4 steps. Today's three-tool surface plus pre-flight summary handles control flow.
- **Cross-source ranking unification** — fixing the OpenAlex / Overton scoring asymmetry properly. Documented as known limitation in §7; needs its own spec (BM25 vs cosine normalization is a real design decision).
- **`run_analysis` handoff payload shape** — covered in §10; deferred to the analysis-integration spec.
- **Auth / project_id handling for `run_analysis` in MCP context** — also in §10; analysis-integration concern.
- **Error handling specifics** — 0-result searches, API failures, partial source outages. These are real concerns but more implementation than spec; the agentic critique flow naturally handles "0 results" by reflecting on why and proposing a refined search.
- **Telemetry for measuring "agentic"-ness** — how to know if the design is working in practice (e.g., critique-acceptance rate, search-to-analysis conversion). Worth tracking but no design decisions blocked on it.

---

## Design principles applied

From Claude Code's tool-use design, translated to MCP:

| Principle | MCP analogue |
|---|---|
| Tool calls are visible turns; opacity is the enemy of trust | Claude Desktop renders every `tools/call` in chat — already works |
| Soft gates over hard gates | Pre-flight summary; user interrupt by typing |
| Reversibility through chat history (scroll == undo) | Chat history preserves all tool results; refined results appear *below* originals |
| No "rewinds" through earlier UI steps | When the user clicks "search" in the picker, they don't get sent *back* to the picker on critique — they get a new search inline |
| Progressive disclosure | Critique surfaces a fix; user accepts (or doesn't) before action |

---

## MCP-specific considerations

- **`_meta.ui.resourceUri` annotations** link each tool to its widget. `search_evidence` → results widget; `suggest_pico_options` → picker widget.
- **Structured output serves two audiences**: `results` for widget rendering, `additional_results` for LLM reasoning. Don't force one schema to serve both.
- **Widget-initiated calls** (`app.callServerTool`) don't reliably surface in host chat. Use `app.sendMessage` + `app.updateModelContext` for hand-offs (picker → search hand-off uses this).
- **Tool result `content` should be terse** — a one-line summary, not a full JSON dump. The LLM uses `structuredContent` for data, not `content`. Otherwise the LLM narrates the dump and duplicates the widget.
- **`CallToolResult` direct return** in FastMCP gives full control over `content` and `structuredContent` separately — bypasses FastMCP's default Pydantic auto-serialisation.

---

## Latency budget reference

| Step | Current | Target |
|---|---|---|
| `suggest_pico_options` (3 parallel LLM calls) | ~3s | unchanged |
| `search_evidence` (multi-query + 12+ source fetches) | ~28s | unchanged |
| Critique (LLM reflection over top-5 + wider 45) | new — est. ~3–5s | <5s |
| End-to-end picker → critique decision | est. ~35–40s | <45s |

The 9s Microsoft p99 threshold is exceeded by `search_evidence` alone (will be addressed via job-handle pattern in a separate spec — out of scope for this one).
