# Policy Atlas MCP Server — Overview

A concise reference for how the MCP server in `backend/app/mcp/` works end-to-end. For the next-stage design (gap analysis, modular `run_analysis` handoff, etc.), see [`spec_search_evidence_agentic.md`](./spec_search_evidence_agentic.md). For the original spike retrospective, see [`mcp_spike_findings.md`](./mcp_spike_findings.md).

---

## What it is

A FastMCP server that exposes the Policy Atlas search pipeline as MCP tools, with interactive UI widgets rendered inline in MCP-Apps-capable hosts (Claude Desktop, MCP Inspector, etc.). Two tools today; a third (`run_analysis`) is specced but not yet wired.

```
┌─────────────────────────┐
│  Claude Desktop / host  │   ← user types a research question
└────────────┬────────────┘
             │  MCP protocol (JSON-RPC over stdio or SSE)
             ▼
┌─────────────────────────┐
│  FastMCP server         │
│  app/mcp/               │
│   ├── server.py         │   ← FastMCP instance, transports, auth
│   ├── tools.py          │   ← tool implementations + widget resources
│   ├── schemas.py        │   ← Pydantic I/O contracts
│   └── widgets/          │   ← Node toolchain (vite + ext-apps SDK)
└────────────┬────────────┘
             │  calls into existing services
             ▼
┌─────────────────────────┐
│  Policy Atlas services  │
│  app/services/...       │   ← SearchWizardService, ReferencesService,
│                         │     OpenAlexService, OvertonService
└─────────────────────────┘
```

---

## The two tools

### `suggest_pico_options(question)`

LLM-generated PICO framings for a research question — 3-5 options each for population, outcome, and inner setting. The host renders these as an interactive picker widget (`widgets/pico-picker.html`).

**Where the LLM enters:** `SearchWizardService` runs three parallel LLM calls (one per facet) via `asyncio.gather`. Returns labels; future work will add descriptions per option.

**Total latency:** ~3s.

### `search_evidence(question, picks, geography, ...)`

Hits OpenAlex (academic literature) and Overton (policy documents) in parallel via `ReferencesService.build_references()`. Returns three layers:

1. **`results`** — top 5 papers (rendered by the search-evidence widget)
2. **`additional_results`** — ~45 more papers as `CompactPaper` (full abstracts, ranking signals) — *for the LLM to reason over*, not rendered
3. **`result_summary`** — aggregate stats (country distribution, year range, source mix, document-type mix, OA fraction) — rendered as a summary strip above the cards *and* used by the LLM for gap-analysis reflection

**Total latency:** ~28s (limited by OpenAlex multi-query + Overton fetches).

**Critical behaviour:** the tool's docstring instructs the LLM to perform a *research gap analysis* post-call using `result_summary` + `additional_results`. Drift, missing methodologies, source-mix asymmetry, and other quality issues become diagnosable.

---

## End-to-end flow

```
1. User: "What works for reducing obesity in UK cities?"
2. Claude → suggest_pico_options(question)
3. Server returns PICO framings + widget URI
4. Host renders pico-picker widget; user ticks options + optional custom inputs
5. Picker widget posts via app.updateModelContext + app.sendMessage:
     - structured PICO picks → invisible LLM context
     - friendly natural-language trigger → chat textbox (user confirms)
6. Claude → search_evidence(question, picks, ...)
7. Server returns top-5 + wider compact set + summary strip + widget URI
8. Host renders search-evidence widget with summary + cards
9. Claude (per docstring) silently does gap analysis using additional_results;
   surfaces concerns + 1 corrective action in chat
10. User confirms or refines; possibly re-run search_evidence with adjusted args
```

---

## Two widgets

Each widget is a self-contained single-file HTML built with vite + `vite-plugin-singlefile` + `@modelcontextprotocol/ext-apps`. The build inlines all JS and CSS so the iframe sandbox can load them without external fetches.

| Widget | Tool | What it shows |
|---|---|---|
| `pico-picker.html` (~348 KB) | `suggest_pico_options` | Checkbox list per facet + "+ add your own…" inputs + Search button |
| `search-evidence.html` (~348 KB) | `search_evidence` | Top-5 cards + aggregate summary strip + animated progress bar during loading |

**Build pipeline** (in `backend/app/mcp/widgets/`):

```bash
npm install                    # one-time
npm run build                  # produces dist/*.html for both widgets
```

The Python server reads the built `dist/*.html` lazily at resource-fetch time (`tools.py` `_read_widget`), so rebuilding the widget doesn't require restarting the Python server — the next tool call serves the new HTML.

**MCP Apps SDK lifecycle inside each widget:**

```typescript
const app = new App({ name, version });
app.ontoolinput = (params) => { /* args available */ };
app.ontoolresult = (result) => { /* structuredContent available */ };
app.onhostcontextchanged = (ctx) => { /* theme, fonts, safe-area */ };
await app.connect();
// later, from button click:
await app.callServerTool({ name, arguments });   // direct tool invocation
await app.sendMessage({ role: "user", content }); // chat hand-off
await app.updateModelContext({ content });        // invisible LLM context
```

---

## Transports

Defined in `server.py`:

| Transport | When to use | Auth |
|---|---|---|
| **stdio** (`run_stdio()`) | Claude Desktop, MCP Inspector — local subprocess | None (local-trusted) |
| **SSE** (`run_sse(port, host)`) | Remote / production deployments | API key via `x-mcp-api-key` header, validated against `settings.MCP_API_KEY` |

stdio is the most common today.

---

## Key design decisions (summary)

For full rationale see [`spec_search_evidence_agentic.md`](./spec_search_evidence_agentic.md). The headline calls:

| Decision | Implementation |
|---|---|
| **Three-stage tool surface** (no per-operation tools) | `suggest_pico_options` (framing) → `search_evidence` (retrieval) → `run_analysis` (deep analysis, planned) |
| **Wider compact set in `additional_results`** | Top-5 rendered by widget; ~45 more carried as `CompactPaper` (with full abstracts up to 1800 chars) for LLM gap analysis |
| **Aggregate `result_summary`** | Country / year / source-mix / doc-type / OA-fraction; widget renders strip, LLM uses for reflection |
| **Cross-source country normalisation** | Deterministic alias map collapses `"USA" + "United States" → "US"` etc. inline in `_compute_result_summary` |
| **Picker → search hand-off via `sendMessage` + `updateModelContext`** | Structured picks invisible in LLM context; user sees friendly trigger pre-filled in chat |
| **Tool docstrings as agent instructions** | Each docstring follows the §12 contract: WHEN / RETURNS / PRESENTATION / POST-CALL / DO-NOT |
| **Known limitation: Overton ranking asymmetry** | Overton docs default to `relevance_score = 0` → systematically deprioritised in merge. Documented in `references.py:756` + `overton.py:144`; agentic critique flags it when relevant. |

---

## Running locally

```bash
# Backend (from repo root)
cd backend
uv sync                                            # install Python deps

# Widget build (one-time, then on every widget source change)
cd app/mcp/widgets
npm install
npm run build                                      # produces dist/pico-picker.html, dist/search-evidence.html

# Run the MCP server (stdio for Claude Desktop)
cd ../../../..
uv run python -m app.mcp.server
```

For Claude Desktop integration, point your config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS) at this server. Use the absolute path to `uv` (GUI-spawned processes don't inherit shell `PATH`), and bake the working directory into the args via `uv run --directory <path>` — `cwd` in the JSON config is unreliable across Claude Desktop versions.

```json
{
  "mcpServers": {
    "policy-atlas": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "run", "--directory", "/abs/path/to/discovery_policy_atlas/backend",
        "python", "-m", "app.mcp.server"
      ]
    }
  }
}
```

After config changes, fully quit Claude Desktop (⌘Q, not just window close) before relaunching.

---

## Where things live

| Path | What's in it |
|---|---|
| `backend/app/mcp/server.py` | FastMCP instance, stdio + SSE transports, API-key auth middleware |
| `backend/app/mcp/tools.py` | `suggest_pico_options` + `search_evidence` implementations, widget resource registrations, helpers (`_row_to_evidence`, `_row_to_compact_paper`, `_compute_result_summary`, `_normalise_country`) |
| `backend/app/mcp/schemas.py` | Pydantic models: `PicoOption`, `SuggestPicoOptionsOutput`, `EvidenceResult`, `CompactPaper`, `ResultSummary`, `SearchEvidenceOutput` |
| `backend/app/mcp/widgets/` | Vite project: TS sources in `src/`, HTML entries at root, built artifacts in `dist/` |
| `backend/app/mcp/widgets/src/pico-picker.ts` | Picker widget logic (checkboxes, custom inputs, sendMessage hand-off) |
| `backend/app/mcp/widgets/src/search-evidence.ts` | Results widget logic (cards, summary strip, doctype chip suppression) |
| `backend/app/core/config.py` | `MCP_API_KEY` setting for SSE auth |
| `~/Library/Logs/Claude/mcp-server-policy-atlas.log` | stderr from the stdio server when run via Claude Desktop — first place to look when something breaks |

---

## Debugging quickstart

| Symptom | Where to look |
|---|---|
| Widget renders empty / iframe blank | DevTools console in the iframe (right-click → Inspect Element); look for `[pico-picker]` or `[search-evidence]` errors |
| Tool call returns error | `~/Library/Logs/Claude/mcp-server-policy-atlas.log` — full Python traceback lands here |
| Overton silently returns 0 results | Same log file — grep for `Reference fetch error (overton_search)` or `Overton semantic search`. Auth, query-format, or geography-filter mismatch are usual causes |
| Stale widget after edit | Rebuild via `npm run build`; re-issue the tool call (no Python restart needed — resource is read lazily) |
| Stale Python behaviour | Restart Claude Desktop fully (⌘Q), not just close window |

---

## What's planned next

See [`spec_search_evidence_agentic.md`](./spec_search_evidence_agentic.md) §10 for the `run_analysis` integration design (currently REST; planned to become a third MCP tool consuming `search_evidence`'s output). The handoff payload shape, auth model, and MCP/REST coexistence are deferred to that spec's next implementation pass.
