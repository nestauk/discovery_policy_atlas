"""Phase 4 — concrete `SourceClient` implementations behind the Phase-3b core.

`broad_search.py` (Phase 3b) depends ONLY on the `SourceClient` Protocol + `Capabilities`
(source.py). This package fills in the two implementations the loop sequences:

  - `openalex_client.OpenAlexSource` — Arm B (this commit): caps all-False; formulation via
    v2's boolean generator; keyword/citation-graph retrieval over OpenAlex; Crossref enrichment.
  - `s2_client.S2Source` — Arm C (next commit): caps all-True; S2 relevance + dense/snippet
    legs, influential-citation forward snowball, native abstracts.

Helpers shared across both:
  - `_cache`   — hash(endpoint+params)→JSON disk cache (resumable; mandatory for S2's 1 req/s).
  - `enrich`   — Arms A/B abstract resolver chain (Crossref MVP + Europe-PMC seam, §4.4).
  - `suggest`  — parametric LLM paper suggestions + source-injected grounding (§4.3 Step 1).
  - `dense_s2` — Arm C dense-query formulation/reformulation (next commit).
  - `_formulation` — the exemplar-block renderer shared by the dense/keyword formulation modules.
"""
