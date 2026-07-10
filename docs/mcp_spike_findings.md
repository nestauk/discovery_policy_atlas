# MCP Integration Spike — Findings

Retrospective companion to [`mcp_integration_plan.md`](./mcp_integration_plan.md). The plan describes what we intended to build; this doc captures what we *learned* doing it.

---

## TL;DR

The spike shipped on plan: a working FastMCP server with two tools (`suggest_pico_options`, `search_evidence`) discoverable by Claude Desktop and the MCP SDK client. End-to-end protocol handshake, tool invocation, and structured response — all confirmed. Three material findings affect production readiness:

1. **`search_evidence` latency is ~28s** — well over Microsoft's 9s p99 validation threshold. Plan called this risk out; now we have a measurement. Mitigation = job-handle pattern (deferred).
2. **`build_references` is HTTP-shaped, not MCP-shaped.** It writes to disk as a side effect. Worked around with a `TemporaryDirectory()`; a clean entry point would be better.
3. **MCP Apps widget rendering in Claude Desktop 1.7196.0 is partial — feature scaffolded but widget content does not display.** Server-side implementation conforms to spec; gap is client-side renderer not yet shipped. See Finding #11.

Everything else is iterable in normal product work.

---

## Measurements

| Operation | Measured latency | Notes |
|---|---|---|
| MCP protocol handshake (initialize) | ~50ms | Well within budget |
| `suggest_pico_options` (3 LLM calls in parallel) | ~3s | OK; fan-out via `asyncio.gather` is load-bearing here |
| `search_evidence` (full multi-query + 12 source fetches) | **~28s** | Over Microsoft's 9s threshold |
| End-to-end chain via MCP SDK client | _filled in below_ | See "Chained test" section |
| Tool registration on server load | <100ms | Decorator-driven |

---

## Findings, grouped

### 1. Latency

- `search_evidence` exceeds the 9s p99 threshold by ~3x. Breakdown: ~6–8s for multi-query LLM generation, ~10–15s for the parallel OpenAlex+Overton fetches, the rest ranking/dedup.
- The CSV write+read round-trip is a non-issue (~50ms in a 28s call).
- Mitigation path is clear: **adopt the job-handle pattern** for `search_evidence` (same shape as `run_analysis`) — sync return when fast, async job handle when slow. This adds 2 tools (`get_search_status`, `get_search_results`) but keeps every individual call inside the budget.

### 2. Service-layer coupling

- `ReferencesService.build_references()` is HTTP/project-shaped: writes `references.csv` and debug JSON files as side effects, returns paths rather than data.
- Workaround in the MCP tool: `tempfile.TemporaryDirectory()` to absorb the side effects with automatic cleanup. Costs ~50ms; auto-cleans on exceptions.
- Clean fix later: add a `write_csv: bool = True` flag to `build_references` so callers can opt out, or extract a pure inner function that returns the DataFrame directly.

### 3. Wizard output is thin for agent consumption

- `generate_population_options` and friends return `list[str]` — just labels, no descriptions.
- In practice the agent (Claude) filled in descriptive context itself ("Who you're studying", "What success looks like"). The descriptions were valuable; they should come from the *tool*, not be reconstructed by the agent.
- **Follow-up:** upgrade wizard prompts to emit `{label, description}` pairs. Touches `prompts.py` + the four wizard methods + their return types. Higher effort, higher value than option count changes.
- `max_options` defaults to 3 — felt thin in agent use. Bumping to 5 in the MCP tool's call to the wizard is a one-line change with no downside.

### 4. Wizard prompts miss obvious domain framings

- For "homelessness in UK cities" the wizard returned 3 populations that all collapsed to "homeless people"; missed framings the agent then flagged (rough sleepers as a UK-specific category, single-adult vs family homelessness, co-occurring mental health & substance use).
- This is a *prompt content* gap, not a tool architecture issue. Real signal for prompt iteration: take Claude's free-of-charge critique and bake it into the wizard's system prompt.

### 5. Geography precision is weak

- Asked for evidence on UK homelessness; top 5 results were predominantly Australian and American. Geography flowed through `search_context` to the boolean-query generator but didn't influence ranking strongly.
- Worth investigating upstream in `references.py`: is `geography` actually getting into the boolean queries, and if so is it appearing as a clause or just metadata?
- Workaround: pass `geography_filter` directly with country codes (the parameter exists). Less clean for an agent caller because it expects ISO codes, not free-text names.

### 6. Agent verbosity / presentation

- Claude Desktop by default added ~3x the volume of useful content as commentary — gap analysis, critique, suggested next steps. Helpful for human chat, undesirable for autonomous agent flows.
- Mitigation applied: explicit `Presentation:` block in each tool's docstring — *"Be concise — no gap analysis, no critique, no suggested next steps. Ask the user which options to pick before calling the next tool; do not proceed autonomously."*
- Compliance is probabilistic, not deterministic — agents partly comply. For Cowork the production system prompt is the real backstop; for Claude Desktop the docstring nudge is the only lever.

### 7. Tool docstrings as protocol surface

- The most surprising finding of the spike: docstrings are **load-bearing agent instructions**, not internal docs. Every word in `suggest_pico_options`'s docstring was visible in Claude's responses — Claude was explaining our design choices to the user verbatim ("The tool's docstring notes that geography gets passed directly to the evidence-search step").
- Pattern to encode going forward: write docstrings *for the agent*. Imperative, specific, concrete exclusions ("no gap analysis") rather than vague guidance ("be concise").

### 8. UI affordances

- Claude Desktop has no native interactive UI (buttons, selects, forms) for tool outputs — everything is markdown text.
- MCP Elicitation primitive exists in spec but client support is patchy (Claude Desktop ~partial, Cowork unclear).
- For Cowork specifically: rich UI is the Microsoft "MCP Apps" widgets path (Phase 3 in the plan). Not portable to Claude Desktop; that's expected.
- Decision: don't chase native picker UI for Claude Desktop. Demos use numbered lists + text picks.

### 9. Progress notifications work and are essential UX

- 28-second tool calls with no progress indicator caused user confusion ("is it stuck?"). Adding four `ctx.info()` markers — bracketing the slow phases in each tool — gives the client a real-time status stream over the MCP `notifications/message` channel.
- FastMCP exposes this via type-annotated `Context` parameter injection: add `ctx: Context | None = None` to the tool signature and FastMCP passes it in automatically. Same pattern as FastAPI's `Request` injection.
- Confirmed working end-to-end through the SDK client: messages arrive in real time as the tool executes, not batched at the end. Claude Desktop renders them as status text under the tool call.
- Notes:
  - `set_logging_level` (client → server subscription) requires the server to declare the `logging` capability, which FastMCP doesn't do by default. Skipping the subscription works fine — server sends regardless, SDK client receives regardless.
  - For finer-grained progress *inside* `build_references` (per-source, per-query), the cleanest path is a logger forwarder that catches existing `app.services.analysis.references` log records and routes them through `ctx.info()`. Deferred — coarse-grained is sufficient for the spike.

### 11. MCP Apps widget rendering — server works, Claude Desktop partial

Built a full MCP Apps widget for `suggest_pico_options` to render PICO options as interactive checkboxes rather than text. Architecture worked end-to-end on the server side; the client (Claude Desktop 1.7196.0, build `2dbd78` from 2026-05-12) acknowledges but does not display.

**What we built:**
- `backend/app/mcp/widgets/pico_picker.html` — vanilla HTML/JS, listens for `ui/notifications/tool-result`, renders three facet sections with checkboxes, submits via `tools/call` postMessage to invoke `search_evidence` with the user's picks
- Resource registered at `ui://policy-atlas/pico-picker` with MIME `text/html;profile=mcp-app` via `@mcp.resource()` in `tools.py`
- `suggest_pico_options` annotated with `meta={"ui": {"resourceUri": PICO_PICKER_URI}}` per spec

**What Claude Desktop 1.7196.0 does:**
- ✅ Reads our `_meta.ui.resourceUri` annotation on the tool definition
- ✅ Tells the LLM "a widget rendered, don't repeat the content" (suppression notice observed in chat output)
- ✅ Reserves vertical space in the chat layout for the iframe
- ❌ **Does not display widget content** — even a minimal debug HTML (bright yellow background, "HELLO FROM WIDGET" banner, JS heartbeat counter, no external dependencies) renders as empty space
- ⚠️ Falls back inconsistently — sometimes Claude renders the structured content as text *anyway*, sometimes leaves the slot blank

**Diagnosis:**
The feature appears scaffolded but not wired up in this Claude Desktop build. Anthropic's MCP Apps documentation explicitly lists Claude as a supported client, but rendering support has not landed (or is gated behind a flag we couldn't find) in the public 1.7196.0 build as of 2026-05-23. Server-side implementation conforms to the spec at `https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx`.

**What this means for the spike:**
- The widget artifact is **shipped and reusable** — when Claude Desktop ships full renderer support, our existing implementation lights up automatically with no server changes.
- The widget should render correctly in `mcp-inspector` (the reference MCP-Apps client) — useful to verify and screenshot for stakeholder demos.
- For other supported clients (ChatGPT, VS Code, Goose, Postman, MCPJam), behaviour will vary; testing required per-client.

**Earlier framing in the plan that should be updated:**
- The plan's "Key risks" table called MCP Apps maturity "Medium" risk — that risk *materialised* for Claude Desktop today. Reality is worse than predicted on that specific row.
- The previous framing in `mcp_integration_plan.md` of MCP Apps widgets as a "Phase 3 / Microsoft Copilot only" concern was wrong on both axes — the spec is supported in principle by Claude Desktop too, but in practice no client we tested rendered widgets in their current ship. The plan should be revised when MCP Apps maturity is re-assessed.

---

### 10. Client-side gotchas (Claude Desktop)

- **`cwd` in the JSON config is unreliable** — sometimes honored, sometimes not, version-dependent. Use `uv run --directory <path>` in the args instead. The flag bakes the directory into the command itself, regardless of how the client spawns it.
- **`command` needs the absolute path to `uv`** — GUI-spawned processes don't inherit shell `PATH`. Use `/opt/homebrew/bin/uv` (or wherever `which uv` reports).
- **Manifest cache** — Claude Desktop needs a full quit-and-restart (⌘Q, not just window close) to pick up server config changes or tool description edits.
- **Logs** — `~/Library/Logs/Claude/mcp-server-<name>.log`. Per-server log file; check first for `ModuleNotFoundError` / handshake failures.

---

## Files shipped

| File | Purpose |
|---|---|
| `backend/app/mcp/__init__.py` | Package docstring |
| `backend/app/mcp/server.py` | FastMCP instance, stdio + SSE transports, API-key auth |
| `backend/app/mcp/schemas.py` | `PicoOption`, `SuggestPicoOptionsOutput`, `EvidenceResult`, `SearchEvidenceOutput` |
| `backend/app/mcp/tools.py` | `suggest_pico_options`, `search_evidence`, helpers |
| `backend/app/core/config.py` (modified) | Added `MCP_API_KEY: Optional[str] = None` |
| `backend/pyproject.toml` (modified) | Added `mcp>=1.0.0` |

---

## Recommended next steps, prioritised

In order of value-per-effort:

1. **Bump `max_options` from 3 → 5** in the `suggest_pico_options` wrapper call. One line; observable quality improvement.
2. **Plan the job-handle redesign for `search_evidence`.** Either as a separate doc or an update to `mcp_integration_plan.md`. Blocker for any production deployment targeting Microsoft store.
3. **Upgrade wizard prompts to emit `{label, description}` pairs.** Eliminates the "agent reconstructs the description" pattern; tightens the tool's contract.
4. **Add a `write_csv: bool = True` flag to `build_references`** (or extract a pure inner function). Lets MCP and any future non-HTTP caller skip the disk round-trip.
5. **Improve geography signal in boolean queries.** Investigate why "UK" returned mostly Australian/US results; likely a prompt-content issue in `references.py`.
6. **Domain-saturate the population wizard prompt** with framings Claude correctly identified as missing (rough sleepers, co-occurring needs, families vs. singles).
7. **Investigate MCP Elicitation maturity** in Claude Desktop and Copilot to see if server-driven user picks are viable yet.

Lower priority / known and deferred:

- **Conditional refinement (`prior_picks` parameter)** — non-breaking optional addition; defer until evidence Cowork makes bad downstream picks.
- **`run_analysis`, `get_job_status`, `get_results`, `chat_with_evidence`** — remaining tools from the plan's full surface. Not in scope for spike.
- **OAuth 2.1 / Entra ID auth** — Phase 2 of the plan; spike used API-key.
- **MCP Apps widgets for Cowork** — Phase 3; not portable to Claude Desktop anyway.

---

## Chained test

End-to-end test: `suggest_pico_options` → first-option-pick (agent stand-in) → `search_evidence`, all via the MCP SDK client (the same harness an autonomous agent would use).

**Question:** "What works for reducing chronic homelessness in UK cities?"

**Timing breakdown:**

| Step | Latency |
|---|---|
| `suggest_pico_options` (3 LLM calls in parallel) | 2.2s |
| `search_evidence` (multi-query + 14 source fetches, 150 unique docs → top 5) | 26.4s |
| MCP protocol overhead (subprocess spawn, handshake, serialisation) | 4.2s |
| **Total wall-clock** | **32.8s** |

**Sample top-5 results:** Goering 2011 (At Home/Chez Soi RCT), Lim 2018 (NYC supportive housing Medicaid impact), Aubry 2020 (permanent supportive housing effectiveness), Marshall 1995 (case-management RCT), Culhane 2002 (public-service cost reductions). Quality is good — these are canonical papers in the housing-first / supportive-housing literature.

**Observations:**

- **Protocol works end-to-end agent-style.** The MCP SDK client spawned our server, completed handshake, called two tools in sequence, parsed both structured responses. That's the Cowork pattern, condensed.
- **Result quality varies run-to-run.** Multi-query generation runs with temperature > 0, so the same question produces different boolean queries each call. Headline results were better than the first solo test (more canonical references, fewer Australian-leaning hits). This is feature not bug for diversity, but worth knowing if reproducibility matters for a particular use case.
- **Geography signal still weak.** Asked for UK cities; got predominantly Canadian/American papers. Reinforces the geography-precision gap noted above.
- **`results_returned: 5` of `total_found: 60`** — the funnel is informing the agent without overflowing its context budget. Exactly the design intent.
