# Policy Atlas MCP Integration Spec

## Context

Policy Atlas is heading towards a world where **Microsoft Copilot Cowork** is the primary consumption surface. Cowork is an autonomous agent (powered by Anthropic's Claude) that plans and executes multi-step workflows inside Microsoft 365. It breaks down a user's request into steps, calls tools autonomously, runs in the background, and checks in at key moments for approval.

This means the MCP server's caller is **an autonomous agent, not a human in a chat**. Policy Atlas provides atomic tools — Cowork decides how to sequence them, when to ask the user for clarification, and when to proceed. The user might say "Research what works for reducing school exclusions and write me a briefing" and Cowork handles the entire orchestration.

### Design principles

1. **Atomic tools, Cowork orchestrates.** We expose focused building blocks. Cowork chains them into workflows.
2. **Stateless server.** Cowork holds working memory across tool calls. We don't maintain session state.
3. **First-time user journey.** The tools assume no prior projects exist. The entry point is a policy question, not a project ID.
4. **Auto-persist on analysis only.** Lightweight search is ephemeral. A project is created only when the full analysis pipeline runs.
5. **Cost controls + action visibility.** Rate limits per user/org. Every tool call and result is logged and auditable.

### Key references

- [Deep research report](./deep-research-report.md) — Copilot extensibility, Entra ID auth, MCP Apps, civil service adoption
- [Microsoft Copilot Cowork announcement](https://www.microsoft.com/en-us/microsoft-365/blog/2026/03/09/copilot-cowork-a-new-way-of-getting-work-done/)
- [MCP in Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp)
- [Build declarative agents with MCP](https://devblogs.microsoft.com/microsoft365dev/build-declarative-agents-for-microsoft-365-copilot-with-mcp/)

---

## Tool surface

### Spike tools (exploration)

| Tool | Purpose | Latency | Consequential |
|---|---|---|---|
| `suggest_pico_options` | Suggest LLM-generated PICO option sets (population, outcome, setting, geography) for a policy question | ~3s | No |
| `search_evidence` | Search OpenAlex/Overton using PICO-structured parameters | ~5-10s | No |

### Full tool surface (post-spike)

| Tool | Purpose | Latency | Consequential |
|---|---|---|---|
| `suggest_pico_options` | Suggest PICO option sets for a policy question | ~3s | No |
| `search_evidence` | Search OpenAlex/Overton using PICO-structured parameters | ~5-10s | No |
| `run_analysis` | Run full pipeline (screen, extract, synthesize). Creates a project. | Immediate return, minutes to complete | **Yes** |
| `get_job_status` | Poll analysis progress | instant | No |
| `get_results` | Retrieve synthesis summary, evidence, interventions from a completed analysis | instant | No |
| `chat_with_evidence` | RAG Q&A over a completed analysis corpus | ~3-5s | No |

Six tools total. Small enough for reliable Cowork orchestration.

> **Design note:** the original draft of this plan had two tools at the front of the pipeline — `extract_pico` (infer PICO from the question) and `generate_options` (suggest refinements per component). We collapsed them into a single `suggest_pico_options` because (a) the existing app does suggestion, not inference, so that's the genuine domain value; (b) Cowork can do shallow text inference itself with a generic prompt — exposing it as a tool adds no value; (c) fewer tools = more reliable orchestration.

---

## Tool specifications

### `suggest_pico_options`

Takes a policy question and returns LLM-suggested option sets for each PICO facet — population, outcome, inner setting, and geography. Cowork (or a human via Cowork's checkpoint) then picks from these to build a structured search.

Generates all facets in a single call (parallel under the hood). This is the genuine domain-value primitive: anyone can run a prompt to *extract* what's literally in the question; the value-add is *suggesting* useful framings (e.g., "SEND in mainstream schools" vs "SEND with EHCP" vs "all at-risk children") that the user might not have phrased themselves but will recognise as the framing they meant.

**Input:**
```json
{
  "question": "What interventions reduce school exclusions for children with SEND in England?"
}
```

**Output:**
```json
{
  "research_question": "What interventions reduce school exclusions for children with SEND in England?",
  "population_options": [
    { "label": "Children with SEND in mainstream schools", "description": "Excludes special schools and PRUs" },
    { "label": "All school-age children at risk of exclusion", "description": "Broader; includes those without SEND diagnosis" },
    { "label": "Children with EHCPs specifically", "description": "Narrower; only those with formal Education, Health and Care Plans" }
  ],
  "outcome_options": [
    { "label": "School exclusion rates", "description": "Permanent and fixed-term exclusions" },
    { "label": "Attendance", "description": "Persistent absence, suspensions" },
    { "label": "Behavioural and wellbeing outcomes", "description": "SEMH measures" }
  ],
  "inner_setting_options": [
    { "label": "Mainstream schools", "description": "" },
    { "label": "Local authority education services", "description": "" },
    { "label": "Alternative provision / PRUs", "description": "" }
  ],
  "geography_options": [
    { "label": "England", "description": "Inferred from the question" }
  ]
}
```

**Key decisions:**
- One tool replaces the original draft's `extract_pico` + `generate_options` pair. Cowork makes one call to get everything.
- Facets are generated **independently** in this spike — i.e. population options are suggested without knowing which outcome will be chosen. Simple, fast, good enough as a starting point.
- Options ordered broad → narrow within each facet (matches existing wizard convention).
- Geography is included as a suggestion (with a single option when it's obvious from the question text) rather than as a separate extraction step — keeps the tool surface uniform.

**Backend:** Thin orchestration over the four existing methods in `app/services/search_wizard.py` (`generate_population_options`, `generate_outcome_options`, `generate_inner_setting_options`, plus a tiny geography helper). Called in parallel via `asyncio.gather` for ~3s total latency. No new prompts needed.

**Deferred enhancements (only if observation justifies them):**
- **Conditional refinement.** Add an optional `prior_picks` parameter so later calls can refine suggestions based on earlier facet picks (e.g., outcome options conditioned on the population the user just chose). Non-breaking change; defer until we see Cowork making poor downstream picks because earlier suggestions weren't conditioned. There's a precedent in the existing code: `AdditionalQuestionsRequest` already takes `population_selected` + `outcome_selected`.
- **Confidence / ambiguity signalling.** Per-facet `confidence` and `ambiguous_components` hints to tell Cowork where to checkpoint. Add only if Cowork's default behaviour proves unreliable.

### `search_evidence`

Searches OpenAlex and/or Overton using structured PICO parameters. Uses our domain-tuned boolean query generation. Returns top results with enough detail for Cowork to summarize or present to the user.

**Input:**
```json
{
  "research_question": "What interventions reduce school exclusions for children with SEND in England?",
  "population": ["children with SEND in mainstream schools"],
  "outcome": ["school exclusion rates"],
  "geography": ["England"],
  "sources": ["openalex", "overton"],
  "max_results": 50
}
```

**Output:**
```json
{
  "total_found": 127,
  "results_returned": 5,
  "results": [
    {
      "doc_id": "openalex:W12345",
      "title": "Reducing exclusions through trauma-informed practice: a cluster RCT",
      "year": 2023,
      "source": "openalex",
      "type": "journal-article",
      "evidence_category": null,
      "authors": ["Smith, J.", "Jones, A."],
      "venue": "British Educational Research Journal",
      "cited_by_count": 45,
      "abstract_snippet": "This cluster-randomised trial evaluated...",
      "is_open_access": true
    }
  ],
  "boolean_queries_used": ["(school exclusion OR permanent exclusion) AND (SEND OR special educational needs) AND (intervention OR programme)"],
  "suggested_actions": [
    "Run full analysis to screen, extract, and synthesize these results",
    "Refine search with narrower population or outcome parameters",
    "Search for systematic reviews specifically"
  ]
}
```

**Key decisions:**
- Returns top 5 results by default (keeps response compact for LLM context)
- `evidence_category` is null at search stage (classification requires the full pipeline)
- `boolean_queries_used` is returned for transparency/auditability
- `suggested_actions` gives Cowork hints about what to do next
- Trusts the orchestrator on scope — no server-side rejection of broad queries
- **Stateless**: Cowork holds these results in working memory. If it later calls `run_analysis`, it passes the results (or re-searches).

**Backend:** Calls `ReferencesService.build_references()` but skips CSV export and project creation. Returns the DataFrame contents directly as JSON.

### `run_analysis` (post-spike)

Triggers the full analysis pipeline: relevance screening, evidence categorization, document acquisition, text extraction, structured data extraction, and synthesis. **Creates a project** as a side effect.

**Input:**
```json
{
  "research_question": "What interventions reduce school exclusions for children with SEND in England?",
  "pico": {
    "population": ["children with SEND in mainstream schools"],
    "outcome": ["school exclusion rates"],
    "geography": ["England"]
  },
  "search_results": [ ... ],
  "sources": ["openalex", "overton"]
}
```

**Output (immediate):**
```json
{
  "project_id": "abc-123",
  "status": "accepted",
  "message": "Analysis started. Use get_job_status to check progress.",
  "estimated_duration_minutes": { "min": 3, "max": 12 }
}
```

**Key decisions:**
- Accepts pre-fetched `search_results` from the search step — does not re-search from scratch
- Creates and persists a project only at this point (not during search)
- Returns immediately with a job handle
- Marked as consequential — Cowork should confirm with the user before running

### `get_job_status` (post-spike)

**Input:** `{ "project_id": "abc-123" }`

**Output:**
```json
{
  "project_id": "abc-123",
  "status": "running",
  "stage_label": "Extracting evidence from documents",
  "progress_percent": 45,
  "eta_seconds": 180,
  "documents_processed": 18,
  "documents_total": 39
}
```

### `get_results` (post-spike)

Retrieves findings from a completed analysis. Compact by default.

**Input:** `{ "project_id": "abc-123" }`

**Output:** Compact synthesis summary — top themes, evidence coverage, key interventions, recommendations, suggested next actions. Target <5KB. No inlined citation quote trees.

### `chat_with_evidence` (post-spike)

RAG Q&A over the vectorized corpus of a completed analysis.

**Input:** `{ "project_id": "abc-123", "question": "Which interventions had the strongest RCT evidence?" }`

**Output:** Answer text + top 3 citations with title, year, supporting quote.

---

## Cowork interaction model

A typical Cowork workflow using these tools:

```
User: "Research what works for reducing school exclusions for SEND children in England"

Cowork plan:
  1. suggest_pico_options("Research what works for reducing school exclusions...")
     → Gets option sets for population, outcome, inner_setting, geography
       in a single call (~3s).
  2. [CHECKPOINT] Present to user: "Here are a few ways I could frame this.
     For population: SEND in mainstream schools, all at-risk children,
     or EHCP children specifically? For outcomes: exclusion rates,
     attendance, behavioural measures?"
     (Cowork may auto-pick high-confidence facets like geography=England.)
  3. User confirms/refines picks.
  4. search_evidence(research_question=..., population=..., outcome=...,
                    inner_setting=..., geography=...)
     → Gets top results.
  5. [CHECKPOINT] "I found 127 papers. Here are the top 5. Want me to run
     a full analysis?"
  6. User approves.
  7. run_analysis(research_question=..., pico=..., search_results=...)
     → Gets job handle.
  8. get_job_status(...) [periodic]
     → Monitors progress.
  9. get_results(...)
     → Gets synthesis summary.
  10. [CHECKPOINT] Present briefing to user with suggested next actions.
```

Policy Atlas controls steps 1, 4, 7-9. Cowork controls the plan, checkpoints, user interaction, and sequencing.

---

## Guardrails

### Cost controls
- Rate limit per user: max N analysis runs per day (configurable per org)
- Rate limit per org: max M concurrent analysis pipelines
- Individual tool calls (extract_pico, search_evidence) are lightweight and don't need hard limits
- Quotas tracked server-side, returned in tool responses when approaching limits

### Action visibility
- Every tool call logged with: timestamp, user_id, org_id, tool_name, input params, response size, latency
- Analysis runs logged with full pipeline audit trail (already exists in Supabase pipeline_timings)
- `boolean_queries_used` returned in search results for transparency
- `evidence_category` reasoning available on request for any screened document

---

## Exploration spike (2 days)

### Goal
Technical validation: prove the MCP server works, schemas are right, tool descriptions produce correct orchestration, and the service layer connects cleanly. Deliverable is a working server testable via Claude Desktop or mcp-inspector, plus a recording for stakeholders.

### Day 1 — Server + suggest_pico_options

**Morning: Scaffolding**
- Add `mcp` Python SDK to `pyproject.toml`
- Create `app/mcp/server.py` with FastMCP, wired for both stdio (local dev) and SSE (remote) transport
- Simple API-key auth guard (replaced by OAuth/Entra later; every non-Microsoft MCP client supports it)
- Verify the server starts and is discoverable by `mcp-inspector`

**Afternoon: `suggest_pico_options`**
- Create `app/mcp/schemas.py` with `SuggestPicoOptionsInput`, `SuggestPicoOptionsOutput`, `PicoOption`
- Create `app/mcp/tools.py` with the tool
- Thin orchestration over the four existing methods in `app/services/search_wizard.py`, parallelised with `asyncio.gather`
- Geography handled by a tiny inline helper (one-shot LLM call or rule-based country detection — simplest thing that works)
- Write the tool description carefully — it's the highest-leverage work in the spike
- Test via Claude Desktop: "Suggest research framings for: What works for reducing homelessness in UK cities?"

### Day 2 — search_evidence + integration test

**Morning: `search_evidence`**
- Wraps `ReferencesService.build_references()`, skipping CSV export and project creation
- Returns top 5 results with metadata (title, year, source, authors, venue, abstract snippet, citation count)
- Input accepts structured PICO parameters from `suggest_pico_options` output (or directly from the agent if it skipped the suggestion step)
- Test: "Search for evidence on school exclusion interventions for SEND children"

**Afternoon: Integration test + documentation**
- End-to-end test: `suggest_pico_options` → `search_evidence` as a chained sequence
- Measure latencies for each tool
- Document: tool schemas, response examples, service-layer gaps found, recommended next steps
- Record a demo showing Claude Desktop using the tools in sequence

### Spike deliverables
- Working MCP server with 2 tools, testable via Claude Desktop / mcp-inspector
- Tool schemas validated against real responses
- Latency measurements for each tool
- Gap notes: what's hard, what needs refactoring in the service layer
- Screen recording for stakeholder demo

### Files created/modified

| File | Change |
|---|---|
| `pyproject.toml` | Add `mcp` SDK dependency |
| `app/mcp/__init__.py` | New package |
| `app/mcp/server.py` | FastMCP server setup, transport config, API-key auth |
| `app/mcp/schemas.py` | `SuggestPicoOptionsInput/Output`, `PicoOption`, `SearchEvidenceInput/Output`, `EvidenceResult` |
| `app/mcp/tools.py` | 2 tool implementations |
| `app/core/config.py` | Add `MCP_API_KEY` setting |

---

## Production roadmap (post-spike)

### Phase 1 — Complete the tool surface (2-3 days)

**Depends on:** Spike complete, gap notes reviewed.

- Add `run_analysis`: accepts pre-fetched search results, creates project, returns job handle
- Add `get_job_status`: wraps existing progress logic from `app/services/analysis/progress.py`
- Add `get_results`: compact synthesis summary from completed analysis
- Add `chat_with_evidence`: wraps existing `ChatService`
- Mark `run_analysis` as consequential
- Implement cost controls: rate limits per user/org, quota tracking
- Implement action logging: structured audit log for every tool call

### Phase 2 — Auth + remote transport (2-3 days)

**Depends on:** Decision on Entra ID app registration.

- Replace API-key auth with OAuth 2.1 / Entra ID SSO
- SSE as primary transport (stdio kept for local dev)
- CORS configuration for Microsoft's widget renderer domain
- Token audience binding per MCP spec (RFC 8707)
- Generate OpenAPI spec as parallel artifact for government security reviews

### Phase 3 — MCP Apps widgets (3-5 days)

**Depends on:** Phase 2 (auth + CORS required).

Three widgets, prioritised by user value:

1. **Evidence explorer** — Filterable table of search results / analysed documents. Sort, filter, browse without re-prompting. This is where the MCP Apps spec adds the most value over text responses.
2. **Policy options comparison** — Side-by-side structured comparison of top interventions: impact score, evidence strength, transferability, risks.
3. **Analysis progress** — Live progress card during `run_analysis`.

Widgets are lightweight HTML/JS served from the MCP server, rendered in Microsoft's sandboxed widget host. No React/Next.js dependency.

### Phase 4 — Declarative agent packaging (2-3 days)

**Depends on:** Phases 1-3 complete.

- Declarative agent manifest (plugin manifest schema v2.4+, `RemoteMCPServer` runtime)
- Store validation: <9s p99 response time, 99.9% availability, privacy/terms documentation
- IT admin deployment guide
- End-to-end test in Copilot Cowork

---

## Key risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Entra ID integration complexity** | High | Spike with API key. Defer Entra until app registration path is decided. |
| **Response size bloats agent context** | Medium | Top 5 results default. Compact schemas. No citation trees. |
| **ReferencesService coupled to CSV/project** | Medium | Spike will expose gaps. May need to extract search logic into a standalone function. |
| **Cowork orchestration unpredictable** | Medium | Invest in tool descriptions. Test with Claude Desktop simulating Cowork-style chaining. |
| **MCP Apps spec still maturing** | Medium | Build widgets as lightweight standalone HTML. Don't couple to framework assumptions. |
| **EU Data Boundary for Anthropic models in Cowork** | Low-Med | Monitor. Flag in admin guide. Not a blocker for spike. |

---

## Compatibility checklist

Decisions made now that keep us aligned with the Copilot Cowork target:

- [x] Atomic tools designed for autonomous agent orchestration
- [x] Stateless server — Cowork manages working memory
- [x] First-time user journey — no prior projects required
- [x] PICO suggestion as a single tool (option-presentation, not inference — matches existing wizard pattern)
- [x] Cost controls and action visibility from Phase 1
- [x] Remote transport (SSE) from day 1
- [x] Tool count within Copilot's recommended limits (6 tools)
- [x] Write tools marked as consequential
- [ ] OAuth 2.1 / Entra ID auth (Phase 2)
- [ ] MCP Apps widgets (Phase 3)
- [ ] Declarative agent manifest (Phase 4)
- [ ] OpenAPI spec as parallel artifact (Phase 2)
