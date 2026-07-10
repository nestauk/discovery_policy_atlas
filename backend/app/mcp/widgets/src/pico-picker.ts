import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import "./pico-picker.css";

type PicoOption = { label: string; description?: string };

type SuggestPicoOptionsOutput = {
  research_question?: string;
  population_options?: PicoOption[];
  outcome_options?: PicoOption[];
  inner_setting_options?: PicoOption[];
};

type FacetSlug = "population" | "outcome" | "inner_setting";

const root = document.getElementById("root") as HTMLElement;

let researchQuestion = "";
let structured: SuggestPicoOptionsOutput = {};
let pending = false;

// User-added free-text options, in addition to the LLM-generated set.
const customOptions: Record<FacetSlug, string[]> = {
  population: [],
  outcome: [],
  inner_setting: [],
};

function handleHostContextChanged(ctx: McpUiHostContext) {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    root.style.padding = `${16 + top}px ${16 + right}px ${16 + bottom}px ${16 + left}px`;
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string),
  );
}

function renderCustomTags(slug: FacetSlug): string {
  return customOptions[slug]
    .map(
      (val, i) => `
      <span class="custom-tag">
        ${escapeHtml(val)}
        <button type="button" data-remove-slug="${slug}" data-remove-idx="${i}" aria-label="Remove">×</button>
      </span>
    `,
    )
    .join("");
}

function renderFacet(title: string, slug: FacetSlug, options?: PicoOption[]): string {
  const items = (options ?? [])
    .map((opt, i) => {
      const id = `${slug}-${i}`;
      const label = opt.label ?? "";
      const desc = opt.description ?? "";
      return `
        <label class="option" for="${id}">
          <input type="checkbox" id="${id}" name="${slug}" value="${escapeHtml(label)}" />
          <span>
            <span class="label">${escapeHtml(label)}</span>
            ${desc ? `<div class="desc">${escapeHtml(desc)}</div>` : ""}
          </span>
        </label>
      `;
    })
    .join("");

  return `
    <div class="facet" data-facet="${slug}">
      <h3>${escapeHtml(title)}</h3>
      ${items || (customOptions[slug].length === 0 ? `<p class="empty" style="padding:6px 4px;text-align:left;">No suggestions — add your own below.</p>` : "")}
      <div data-tags="${slug}">${renderCustomTags(slug)}</div>
      <div class="custom-row">
        <input type="text" data-custom-slug="${slug}" placeholder="+ add your own ${title.toLowerCase()}…" />
        <button type="button" data-add-slug="${slug}">Add</button>
      </div>
    </div>
  `;
}

function gatherSelections(slug: FacetSlug): string[] {
  const checked = Array.from(
    document.querySelectorAll<HTMLInputElement>(`input[name="${slug}"]:checked`),
  ).map((el) => el.value);
  return [...checked, ...customOptions[slug]];
}

function setStatus(text: string) {
  const el = document.getElementById("status");
  if (el) el.textContent = text;
}

function addCustomOption(slug: FacetSlug) {
  const input = document.querySelector<HTMLInputElement>(
    `input[data-custom-slug="${slug}"]`,
  );
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;
  if (customOptions[slug].includes(val)) {
    input.value = "";
    return;
  }
  customOptions[slug].push(val);
  input.value = "";
  refreshTags(slug);
}

function removeCustomOption(slug: FacetSlug, idx: number) {
  customOptions[slug].splice(idx, 1);
  refreshTags(slug);
}

function refreshTags(slug: FacetSlug) {
  const container = document.querySelector<HTMLElement>(`[data-tags="${slug}"]`);
  if (container) container.innerHTML = renderCustomTags(slug);
}

function bindEvents() {
  root.addEventListener("click", (ev) => {
    const target = ev.target as HTMLElement;
    const addSlug = target.dataset.addSlug as FacetSlug | undefined;
    if (addSlug) {
      addCustomOption(addSlug);
      return;
    }
    const removeSlug = target.dataset.removeSlug as FacetSlug | undefined;
    if (removeSlug && target.dataset.removeIdx != null) {
      removeCustomOption(removeSlug, Number(target.dataset.removeIdx));
      return;
    }
    if (target.id === "search-btn") {
      submitSearch();
    }
  });

  root.addEventListener("keydown", (ev) => {
    const target = ev.target as HTMLElement;
    if (
      ev.key === "Enter" &&
      target instanceof HTMLInputElement &&
      target.dataset.customSlug
    ) {
      ev.preventDefault();
      addCustomOption(target.dataset.customSlug as FacetSlug);
    }
  });
}

function render() {
  const data = structured;
  root.innerHTML = `
    <h2>Frame your research</h2>
    <p class="subtitle">${
      researchQuestion
        ? escapeHtml(researchQuestion)
        : "Pick one or more options per facet, add your own if needed, then submit."
    }</p>
    ${renderFacet("Population", "population", data.population_options)}
    ${renderFacet("Outcome", "outcome", data.outcome_options)}
    ${renderFacet("Inner setting", "inner_setting", data.inner_setting_options)}
    <div class="actions">
      <button class="primary" id="search-btn">Search evidence</button>
      <span class="status" id="status"></span>
    </div>
  `;
}

// Structured picks intended for the LLM, not the user. Shipped via
// updateModelContext so they never appear in the chat textbox.
function buildContextBlock(
  question: string,
  population: string[],
  outcome: string[],
  inner_setting: string[],
): string {
  const fmt = (label: string, vals: string[]) =>
    vals.length === 0 ? `${label}: (any)` : `${label}: ${vals.join("; ")}`;
  return [
    `The user is framing a research search with the PICO picker.`,
    `When they ask you to search next, call the search_evidence tool with these exact arguments:`,
    `- research_question: "${question}"`,
    `- ${fmt("population", population)}`,
    `- ${fmt("outcome", outcome)}`,
    `- ${fmt("inner_setting", inner_setting)}`,
    `- max_results: 5`,
    `- total_limit: 30`,
  ].join("\n");
}

// Short natural-language trigger the user will see pre-filled in the chat
// input. Kept friendly so it's coherent if they press send as-is.
function buildTrigger(question: string): string {
  return `Search the evidence for "${question}" using the framings I picked.`;
}

async function submitSearch() {
  if (pending) return;
  if (!researchQuestion) {
    setStatus("No research question received from host.");
    return;
  }
  const btn = document.getElementById("search-btn") as HTMLButtonElement | null;
  if (!btn) return;

  pending = true;
  btn.disabled = true;
  setStatus("Sending to assistant…");

  const contextBlock = buildContextBlock(
    researchQuestion,
    gatherSelections("population"),
    gatherSelections("outcome"),
    gatherSelections("inner_setting"),
  );
  const trigger = buildTrigger(researchQuestion);

  try {
    // Order matters: ship the structured picks into model context first, then
    // send the visible trigger. If the trigger landed first the LLM might call
    // search_evidence before the picks are available to reason over.
    await app.updateModelContext({
      content: [{ type: "text", text: contextBlock }],
    });
    const { isError } = await app.sendMessage({
      role: "user",
      content: [{ type: "text", text: trigger }],
    });
    if (isError) {
      setStatus("Host rejected the message.");
      btn.disabled = false;
      pending = false;
      return;
    }
    setStatus("Sent — results will appear in chat.");
    // Leave the button disabled: the picker has done its job for this round.
  } catch (e) {
    setStatus(`Send failed: ${e instanceof Error ? e.message : String(e)}`);
    btn.disabled = false;
    pending = false;
  }
}

const app = new App({ name: "PICO Picker", version: "0.1.0" });

app.ontoolinput = (params) => {
  const args = (params.arguments ?? {}) as { question?: string };
  researchQuestion = args.question ?? "";
};

app.ontoolresult = (result) => {
  structured = (result.structuredContent ?? {}) as SuggestPicoOptionsOutput;
  if (!researchQuestion && structured.research_question) {
    researchQuestion = structured.research_question;
  }
  render();
};

app.onhostcontextchanged = handleHostContextChanged;
app.onerror = (err) => console.error("[pico-picker]", err);

bindEvents();

app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx) handleHostContextChanged(ctx);
});
