import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import "./search-evidence.css";

type EvidenceResult = {
  doc_id?: string;
  title?: string;
  year?: number | null;
  source?: string | null;
  document_type?: string | null;
  authors?: string[];
  venue?: string | null;
  cited_by_count?: number | null;
  abstract_snippet?: string | null;
  is_open_access?: boolean | null;
  landing_page_url?: string | null;
};

type ResultSummary = {
  country_distribution?: Record<string, number>;
  year_range?: [number, number] | null;
  year_median?: number | null;
  source_mix?: Record<string, number>;
  document_type_mix?: Record<string, number>;
  open_access_fraction?: number | null;
};

type SearchEvidenceOutput = {
  total_found?: number;
  results_returned?: number;
  results?: EvidenceResult[];
  result_summary?: ResultSummary | null;
  boolean_queries_used?: string[];
};

const root = document.getElementById("root") as HTMLElement;

let structured: SearchEvidenceOutput = {};
let researchQuestion = "";

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string),
  );
}

function formatAuthors(authors?: string[]): string {
  if (!authors || authors.length === 0) return "";
  if (authors.length === 1) return authors[0];
  if (authors.length === 2) return authors.join(" & ");
  return `${authors[0]} et al.`;
}

// Turn OpenAlex/Overton-style codes like "journal-article" into "Journal Article".
// Deterministic, no LLM — these strings come straight from the source.
function humaniseDocType(raw?: string | null): string {
  if (!raw) return "";
  return raw
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Uninformative values to suppress — OpenAlex sometimes emits "unknown" as
// type_crossref when it has no signal; rendering that as a chip looks like a
// category label (visually identical to the old evidence-category "Unknown"
// badge we removed). A missing chip is better than a misleading one.
const _UNINFORMATIVE_DOCTYPE = new Set(["unknown", "other", "n/a", "none", ""]);

function renderDocTypeChip(doc_type?: string | null): string {
  if (!doc_type) return "";
  if (_UNINFORMATIVE_DOCTYPE.has(doc_type.trim().toLowerCase())) return "";
  const label = humaniseDocType(doc_type);
  if (!label) return "";
  return `<span class="doctype-chip">${escapeHtml(label)}</span>`;
}

// Render the aggregate summary strip from result_summary. Computed server-side
// over the FULL fetched set (not just top-N). See docs/spec_search_evidence_agentic.md §8.
function renderSummaryStrip(summary?: ResultSummary | null): string {
  if (!summary) return "";

  const parts: string[] = [];

  // Country distribution: top-2 by share + "other" rolled up.
  const countries = summary.country_distribution ?? {};
  const totalC = Object.values(countries).reduce((a, b) => a + b, 0);
  if (totalC > 0) {
    const sorted = Object.entries(countries).sort((a, b) => b[1] - a[1]);
    const pct = (n: number) => Math.round((n / totalC) * 100);
    const items = sorted.slice(0, 2).map(([k, v]) => `${pct(v)}% ${k}`);
    const otherCount = sorted.slice(2).reduce((s, [, c]) => s + c, 0);
    if (otherCount > 0) items.push(`${pct(otherCount)}% other`);
    parts.push(items.join(" · "));
  }

  // Year range + median.
  if (summary.year_range) {
    const [yMin, yMax] = summary.year_range;
    parts.push(
      summary.year_median != null
        ? `${yMin}–${yMax} (median ${summary.year_median})`
        : `${yMin}–${yMax}`,
    );
  }

  // Source mix — map known keys to friendlier labels; keep counts.
  const sources = summary.source_mix ?? {};
  const sourceLabel: Record<string, string> = {
    openalex: "academic",
    overton: "policy",
  };
  const sourceParts = Object.entries(sources)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${sourceLabel[k] ?? k}`);
  if (sourceParts.length > 0) parts.push(sourceParts.join(" / "));

  // Open-access fraction when known.
  if (summary.open_access_fraction != null) {
    const oaPct = Math.round(summary.open_access_fraction * 100);
    parts.push(`${oaPct}% open access`);
  }

  if (parts.length === 0) return "";
  return `<p class="summary-strip">${escapeHtml(parts.join(" · "))}</p>`;
}

function renderResult(r: EvidenceResult, idx: number): string {
  const title = r.title || "Untitled";
  const metaText = [
    r.year != null ? String(r.year) : null,
    formatAuthors(r.authors),
    r.venue,
    r.cited_by_count != null ? `cited by ${r.cited_by_count}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const abstract = r.abstract_snippet ?? "";
  const link = r.landing_page_url
    ? `<a class="open" href="${escapeHtml(r.landing_page_url)}" target="_blank" rel="noopener noreferrer">Open ↗</a>`
    : "";
  const oa = r.is_open_access ? `<span class="badge">Open access</span>` : "";
  const chip = renderDocTypeChip(r.document_type);

  // Chip inlines at the start of the meta line, grouping "at a glance"
  // signals together (type · year · authors · venue · citations · OA).
  const metaInner = [chip, metaText ? escapeHtml(metaText) : "", oa]
    .filter(Boolean)
    .join(" ");
  const metaLine = metaInner ? `<p class="meta">${metaInner}</p>` : "";

  return `
    <li class="result">
      <div class="result-head">
        <span class="num">${idx + 1}</span>
        <h3 class="title">${escapeHtml(title)}</h3>
      </div>
      ${metaLine}
      ${abstract ? `<p class="abstract">${escapeHtml(abstract)}</p>` : ""}
      ${link}
    </li>
  `;
}

// Updates the loading view in place if ontoolinput has given us the question.
// The initial loading markup ships in the static HTML (search-evidence.html)
// so the progress bar renders the moment the iframe mounts — many hosts
// (notably Claude Desktop) don't fire ontoolinput before ontoolresult, so
// relying on it alone left the bar invisible.
function updateLoadingQuestion() {
  if (!researchQuestion) return;
  const textEl = root.querySelector<HTMLElement>(".loading-text");
  if (textEl) {
    textEl.innerHTML = `Searching evidence for <strong>"${escapeHtml(researchQuestion)}"</strong>…`;
  }
}

function renderResults() {
  const data = structured;
  const total = data.total_found ?? 0;
  const results = data.results ?? [];
  const returned = results.length;

  if (returned === 0) {
    const q = researchQuestion ? ` for "${escapeHtml(researchQuestion)}"` : "";
    root.innerHTML = `<p class="empty">No matching evidence found${q}.</p>`;
    return;
  }

  root.innerHTML = `
    <header class="head">
      <h2>Evidence results</h2>
      <p class="subtitle">Found ${total} papers · showing top ${returned}</p>
      ${renderSummaryStrip(data.result_summary)}
    </header>
    <ol class="results">
      ${results.map(renderResult).join("")}
    </ol>
  `;
}

function handleHostContextChanged(ctx: McpUiHostContext) {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    root.style.padding = `${16 + top}px ${16 + right}px ${16 + bottom}px ${16 + left}px`;
  }
}

const app = new App({ name: "Search Evidence Results", version: "0.1.0" });

app.ontoolinput = (params) => {
  const args = (params.arguments ?? {}) as { research_question?: string };
  researchQuestion = args.research_question ?? "";
  updateLoadingQuestion();
};

app.ontoolresult = (result) => {
  structured = (result.structuredContent ?? {}) as SearchEvidenceOutput;
  renderResults();
};

app.onhostcontextchanged = handleHostContextChanged;
app.onerror = (err) => console.error("[search-evidence]", err);

app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx) handleHostContextChanged(ctx);
});
