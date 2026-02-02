# Impact assessment

Impact assessment answers (per intervention and outcome):

- **Does it work?** (directional consensus)
- **How much does it work?** (magnitude estimate)
- **How strong is the causal claim?** (causal reliability / mechanism)
- **Will it work here?** (transferability / structural fit)
- **What could go wrong?** (risk assessment)

## Core principle: impact is a vector, not a scalar

We do **not** produce a single “impact score”. Instead, we produce a structured **Impact Profile** assembled from:

- **Tier 1 (“Reader”)**: document-level, factual extraction.
- **Tier 2 (“Judge”)**: cross-document synthesis using evidence-quality weighting.

The system receives an **evidence quality score** (Int 1–5) for each document from the parallel Evidence Assessment module. This score is used as a **weighting factor** during synthesis (it is not re-calculated here).

## Inputs and outputs

### Inputs

- **Documents** (papers / reports) and associated metadata.
- **Tier 1 extractions** (atomic signals per document).
- **Evidence quality scores** (1–5) per document.
- **User target context** (from the search wizard / project `search_query`), e.g.:
  - population
  - inner setting (delivery environment)
  - geography (evidence sourcing)
  - **transferability target geography is fixed to UK** for Policy Atlas users
  - implementation constraints (optional): cost, staffing, implementation complexity

### Outputs

- **Outcome-level impact profile**:
  - verdict label + explanation
  - discord/contested flag + reason (where applicable)
  - predicted magnitude + structured magnitude detail (direction, bucket counts, source/measurement counts, thresholds)
  - causal mechanism (attribution / contribution / correlation) + structured support counts
  - per-outcome **consensus meter** (directional evidence counts) in the UI
- **Intervention-level transferability**:
  - **Context Fit** rating + breakdown (inner setting, population, geography; target geography fixed to UK)
  - **Implementation requirements** rating (Low/Medium/High/Unknown) derived from evidence levels
  - Implementation dimensions always show **evidence levels** (low/moderate/high/unknown)
  - When user tolerances are provided, show an **exceeds tolerance** flag per dimension
  - Badge always shows requirements rating; warning indicator appears if any dimension exceeds tolerance
  - LLM-based explanations per dimension are stored in breakdown notes (context similarity + evidence/tolerance alignment)
- **Risk profile**:
  - clustered risk themes
  - harm warning flag (where thresholds are met; UI may choose not to surface the label)
  - linkage between risks and the relevant intervention themes

## Tier 1 (“Reader”): atomic extraction per document

Tier 1 runs a multi-stage extraction pipeline:

`extract_issues → extract_interventions → extract_mappings → extract_results → extract_conclusions`

### Results (outcomes per intervention)

Tier 1 extracts factual outcome signals and how they are framed in the document:

- **effect_direction**: `increase | decrease | null | mixed | inconclusive`
- **effect_size_type**: raw metric label (e.g., “Cohen’s d”, “OR”)
- **effect_size**: raw value (e.g., “0.3 SD”, “15%”, “OR 0.85”)
- **causality_claim**: `attribution | contribution | correlation`
- **negative_impact_flag**: boolean (true if harm / adverse effects are indicated)
- supporting quote(s)

Important: **semantic magnitude bucketing is intentionally deferred**. Tier 1 extracts raw values and claims without cross-document calibration.

### Interventions (implementation profile)

Tier 1 extracts the intervention plus CFIR-inspired delivery characteristics:

- **country** (outer setting proxy)
- **population_intervened** (beneficiary proxy)
- **population_demographics**
- **inner_setting** (e.g., School, Clinical/Hospital, Prison, Community)
- **cost_level** + justification
- **staffing_level** + justification
- **implementation_complexity_level** + justification
- supporting quote(s)

### Conclusions (document-level risk assessment)

Conclusions include:

- **evidence_strength** (methodological quality rating)
- **risk_assessment**:
  - risks identified + unintended consequences flag
    - risks are **intervention-related** (harms, adverse effects, implementation challenges)
    - do **not** include the underlying problem the intervention is trying to solve

## Tier 2 (“Judge”): cross-document synthesis

Tier 2 consumes Tier 1 extractions and produces theme-level synthesis with evidence-quality weighted logic.

### High-level workflow

1. **Load**
   - Load raw extractions and document evidence-quality scores.

2. **Canonical concept creation**
   - Create canonical concepts for clustering.
  - Extract **risk concepts** from:
    - conclusion risk assessment (`risks_identified`)
     - results marked with `negative_impact_flag=true`
   - Load **target context** (inner setting / population) from project `search_query`.
   - Transferability geography is evaluated against a fixed UK target context.

3. **Theme discovery (parallel)**
   - issue themes
   - intervention themes
   - outcome themes
   - risk themes (clustered similarly to outcomes)

4. **Aggregation**
   - Compute **quality-weighted** counts for outcomes:
     - positive/negative/null buckets are sums of (evidence quality score / 5), rounded up to whole numbers
   - Select representative effect sizes (quality-prioritised, numeric-biased, deduplicated).
   - Build theme→extraction ID mappings to scope transferability to assigned extractions.

5. **Impact synthesis (enrichment)**
   - Compute and attach:
     - verdict label + explanation (evidence-based direction labels)
     - discord flag + reason (contested evidence)
  - predicted magnitude + structured magnitude detail (direction, bucket counts, sources, measurements, dominant scale, thresholds)
    - transferability rating + breakdown (6 dimensions; target geography fixed to UK)
   - inner setting / population / geography use LLM semantic similarity (default model: GPT-4o-mini)
   - cost / staffing / implementation complexity use ordinal tolerance comparison; add LLM explanation of tolerance alignment
     - risk themes linked to interventions + harm warning flag

## Synthesis rules and guardrails

### Transferability match levels

Each transferability dimension uses a 6-level scale:

- `match`
- `similar`
- `comparable`
- `partial`
- `mismatch`
- `unknown`

### Verdict labels (direction + evidence strength)

Verdicts communicate **direction** and **evidence strength** (not magnitude or causality):

- `well_evidenced_increase` / `well_evidenced_decrease`
- `evidenced_increase` / `evidenced_decrease`
- `suggested_increase` / `suggested_decrease`
- `contested`, `no_effect`, `insufficient_evidence`, `probable_contribution`

Direction should be interpreted in outcome context (e.g., a decrease in obesity is a positive result).

### Null vs “no data”

- **null** = confirmed no-effect result and should count as evidence (weighted).
- **no data** = absent evidence and should not contribute to any bucket.

### Discord / contested evidence

If evidence is meaningfully split between positive and negative directions, mark the outcome as **contested** and record the reason.

### Magnitude prudence

If magnitude signals are tied or ambiguous, prefer the **lower** bucket (“prudence check”) rather than overstating impact.

### Negative impact / harm warning

If unintended consequences are flagged in a sufficiently large fraction of high-quality sources, raise a **harm warning** for the associated risk theme.

### Contribution fallback

Where strong “well evidenced” verdicts would imply causal certainty but **attribution-quality evidence is absent**, downgrade the verdict to avoid overstating causal certainty.

## Persistence (database)

Tier 2 persists synthesis results into Supabase tables (see the migration work in the Tier 2–4 plans):

- `synthesis_themes`
  - supports risk themes via `theme_type='risk'`
  - stores transferability fields (and, for risks, harm warning + primary linkage to interventions)
- `theme_intervention_links`
  - many-to-many links between risk/issue themes and intervention themes (primary + secondary links)
- `synthesis_outcome_themes`
  - stores verdict and magnitude fields for outcome themes
  - **one row per intervention–outcome pair** (same outcome can appear under multiple interventions)
  - links outcomes to interventions via `intervention_theme_id`
  - causal mechanism fields belong at outcome granularity (intervention–outcome), not only intervention level
  - magnitude and causal detail fields are stored as JSON

Operational note: apply the relevant migration(s) before expecting new synthesis fields to appear in stored summaries.

## API and frontend usage

### Search wizard: target inner setting

The search wizard can suggest and collect a user’s **inner setting** (delivery environment). This becomes part of the project `search_query` and is consumed by Tier 2 transferability scoring.

### Synthesis summary payload

The API should expose (and the frontend can display):

- outcome verdicts (label + description)
- discord flags (contested evidence)
- magnitude estimate + structured magnitude detail
- causal mechanism at outcome level + structured support counts
- transferability rating + breakdown at intervention level
- risk themes + harm warnings linked back to interventions

## Operational notes

- **Re-synthesis after changes**: when synthesis logic changes, re-run synthesis for target projects to repopulate cached summaries.
- **Backfilling**: consider whether historical projects need backfilled Impact Profile fields to avoid empty UI on older analyses.

## Impact summary text (intervention-level)

Intervention-level `impact_summary` is generated by an LLM to synthesise the impact profile:

- summarises overall evidence direction and confidence
- highlights contested or uncertain outcomes
- **explicitly addresses user-specified outcomes** if provided in the search wizard
- references the **research question** to keep the summary focused and direct

## Notes on legacy scores

Some parts of the UI still show legacy scalar scores (e.g., average impact/evidence star ratings). These should not be treated as the Impact Profile; the Impact Profile is the outcome-level vector described above.


