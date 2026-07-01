# Code-reuse rationale — why this experiment ports rather than imports

> **Status:** design rationale, written 2026-06-17. Companion to
> [`README.md`](../README.md) and the spec
> ([`docs/specs/spec_retrieval_experiment_openalex.md`](../../../../../docs/specs/spec_retrieval_experiment_openalex.md)).

## The question

> "There's an argument that we're reproducing a bunch of code that already lives
> in another package, right?"

Yes — and that's true in **two different senses**, which deserve separate verdicts.
This document records the reasoning so the approach is defensible in review and so the
one genuine risk (Phase 4) is decided deliberately rather than by accident.

---

## Sense 1 — porting external packages (PF + BENCH)

Most of the experiment's logic is a deliberate, one-directional **port** of two
external repos, *acknowledged in the module docstrings themselves*:

| Experiment module | Ported from | What it is |
| --- | --- | --- |
| `query_analysis.py` | **PF** (`asta-paper-finder`) | content / recency / centrality extraction |
| `ranking.py` | **PF** | ranking sigmoids + Cohere rerank client |
| `judge.py` | **PF** + **BENCH** | criteria extraction (PF) + per-paper scoring (BENCH) |
| `metrics.py` | **BENCH** (`asta-bench`) | ~100-line verbatim port of the metric formulas |

### Why port instead of `import`

`metrics.py` answers this directly:

> *"Why reimplement instead of import BENCH? BENCH pulls in `inspect-ai` + a
> HuggingFace dataset download for its normalizer reference; we only need ~10 pure
> functions. So we port them verbatim (~100 lines) and pin parity with
> `test_metrics.py`."*

The standard objection to duplication is **DRY**, but DRY's real cost is *drift* —
two copies that both keep evolving and silently diverge. That cost is bought down here:

1. **The dependency is heavyweight, the slice is thin.** Taking `inspect-ai` + an HF
   dataset download as a transitive dependency of a *research experiment* is a far worse
   trade than vendoring ~100 lines of pure functions.
2. **The copy is frozen, not a live fork.** The experiment's whole design is a *frozen
   operating point* (`CONFIG` is "frozen for the experiment's duration"). A snapshot that
   isn't meant to track upstream doesn't carry DRY's drift cost in the usual way.
3. **Parity is pinned by tests.** `tests/test_metrics.py` asserts the port against
   hand-computed values from the BENCH source (k_est worked examples, `find_dcg`'s
   log discount, corrected-nDCG bounds, 0–3 bucketing). The duplication is *checked*,
   not hoped-for.

**Verdict:** this is "vendor-the-slice-you-need-with-parity-tests" — a legitimate
pattern, and the right call here. Where reuse *is* cheap (LLM calls via the backend's
`get_llm` / `LLMProcessor`, the Cohere client) the experiment already lazy-imports the
backend rather than copying it.

---

## Sense 2 — overlap with our *own* backend (the real one to watch)

The sharper version of the concern is not PF/BENCH but **our own `backend`**, which
already ships retrieval code:

- `app/services/openalex.py` — `OpenAlexService` (523 LOC): query sanitisation,
  polite-pool email (`settings.OPENALEX_EMAIL`), cursor pagination, `search` /
  `search_minimal` / `search_multi_query`.
- `app/services/search_wizard.py` — search orchestration.
- `app/services/synthesis/nodes/rag_retrieval.py`, `synthesis/tools/search.py` — retrieval.

Today this overlap is **well-managed**:

- The experiment is a self-contained `uv` project with `backend` as an editable path
  dependency, so **Arm A is a thin wrapper over the real `OpenAlexService`** — it reuses
  production code rather than copying it (see `README.md`).
- `source.py` defines a `SourceClient` *protocol* (the seam), not a second OpenAlex
  client. The only concrete implementation so far is `FakeSource` (offline, deterministic).

### Where it could bite: Phase 4

`source.py` states that **Phase 4 will add concrete OpenAlex/S2 clients implementing
`SourceClient`**. That is the moment a *second OpenAlex client* could appear in the
experiment, parallel to the production one. Comparing the surfaces:

| `SourceClient` method | Already in `OpenAlexService`? |
| --- | --- |
| `keyword_search(query, limit)` | **Yes** — `search` / `search_minimal` / `search_multi_query` (+ sanitisation, polite pool, pagination) |
| `formulate_queries`, `suggest`, `reformulate` | No — these are PF LLM mechanisms |
| `dense_search` | No — Arm C / S2 only |
| `fetch_references`, `fetch_citations` | No — backend has no citation traversal |

So the genuine overlap is narrow: **`keyword_search` and the OpenAlex plumbing it sits
on** (sanitisation, polite-pool email, pagination). Everything else is either new
(citation traversal, dense leg) or PF mechanism that doesn't exist in the backend.

### Recommendation for Phase 4

**Wrap, don't reimplement, for the OpenAlex keyword leg.** The OpenAlex `SourceClient`
should adapt `OpenAlexService` to the protocol (mapping its rows to `Candidate`) rather
than re-issuing raw OpenAlex calls. This keeps a single source of truth for the parts
that are easy to get subtly wrong and that *do* keep evolving — query sanitisation, the
polite-pool email (which `config.py` already cares about: 10 req/s vs the throttled
common pool), and cursor pagination. The new primitives the backend lacks
(`fetch_references` / `fetch_citations`) are genuinely additive and belong in the
experiment.

This is the one place where DRY actually bites — both sides keep evolving — so it's
worth deciding on purpose.

---

## One-paragraph summary (for a PR description / reviewer)

The experiment reproduces code in two senses. The PF/BENCH ports
(`metrics.py`, `ranking.py`, `judge.py`, `query_analysis.py`) are a deliberate
*vendor-the-thin-slice* decision: importing upstream would drag in `inspect-ai` + an HF
dataset download for ~10 pure functions, the copy is frozen for the experiment's
lifetime, and `tests/test_metrics.py` pins parity — so the usual DRY drift cost doesn't
apply. Overlap with our own `backend` is currently minimal: Arm A wraps the real
`OpenAlexService`, and `source.py` defines a protocol seam, not a second client. The only
forward-looking risk is Phase 4's concrete OpenAlex client, where the keyword leg should
*wrap* `OpenAlexService` (single source of truth for sanitisation / polite pool /
pagination) rather than reimplement it.
