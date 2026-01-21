# Impact assessment (Next-Gen Impact Evaluation, v2.2)

This document describes the Impact Assessment process in Policy Atlas, based on:

- `docs/backend/impact_assessment_plan.md` (spec v2.2)
- `docs/backend/impact_assessment_tier_1.md`
- `docs/backend/impact_assessment_tier_2.md`
- `docs/backend/impact_assessment_tier_3.md`
- `docs/backend/impact_assessment_tier_4.md`

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

### Outputs

- **Outcome-level impact profile**:
  - verdict label + explanation
  - discord/contested flag + reason (where applicable)
  - predicted magnitude + confidence text
  - causal mechanism (attribution / contribution / correlation) and detail (Tier 2; may be refined further in Tier 4)
  - per-outcome **consensus meter** (directional evidence counts) in the UI
- **Intervention-level context fit**:
  - transferability rating + breakdown (inner setting, population, geography, resource intensity, delivery complexity; target geography fixed to UK)
  - LLM-based similarity explanations per dimension (stored in breakdown notes)
- **Risk profile**:
  - clustered risk themes
  - harm warnings (where thresholds are met)
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
- **resource_intensity**
- **delivery_complexity**
- supporting quote(s)

### Conclusions (document-level impact vector)

Conclusions include:

- **evidence_strength** (methodological quality rating)
- **predicted_impact** evolved into a structured **ImpactPrediction** vector:
  - magnitude estimate + justification (preliminary)
  - causal reliability + justification (document-level, if available)
  - transferability notes
  - risks identified + unintended consequences flag
    - risks are **intervention-related** (harms, adverse effects, implementation challenges)
    - do **not** include the underlying problem the intervention is trying to solve

Backwards compatibility: older scalar `predicted_impact` shapes should be migrated into the new structure via a helper (Tier 1 plan).

## Tier 2 (“Judge”): cross-document synthesis

Tier 2 consumes Tier 1 extractions and produces theme-level synthesis with evidence-quality weighted logic.

### High-level workflow

1. **Load**
   - Load raw extractions and document evidence-quality scores.

2. **Canonical concept creation**
   - Create canonical concepts for clustering.
   - Extract **risk concepts** from:
     - conclusion predicted impact risks (`risks_identified`)
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
     - positive/negative/null buckets are sums of evidence quality scores
   - Select representative effect sizes (quality-prioritised, numeric-biased, deduplicated).

5. **Impact synthesis (enrichment)**
   - Compute and attach:
     - verdict label + explanation
     - discord flag + reason (contested evidence)
     - predicted magnitude + confidence text (hybrid, effect-size aware; confidence counts effect-size measurements and also reports the number of unique sources)
    - transferability rating + breakdown (5 dimensions; target geography fixed to UK)
    - inner setting / population / geography use LLM semantic similarity (default model: GPT-4o-mini)
    - resource intensity and delivery complexity targets are currently defaulted
     - risk themes linked to interventions + harm warning flag

## Synthesis rules and guardrails

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

Where strong “high confidence” verdicts would imply causal certainty but **attribution-quality evidence is absent**, downgrade the verdict to avoid overstating causal certainty.

## Persistence (database)

Tier 2 persists synthesis results into Supabase tables (see the migration work in the Tier 2–4 plans):

- `synthesis_themes`
  - supports risk themes via `theme_type='risk'`
  - stores transferability fields (and, for risks, harm warning + linkage to interventions)
- `synthesis_outcome_themes`
  - stores verdict and magnitude fields for outcome themes
  - **one row per intervention–outcome pair** (same outcome can appear under multiple interventions)
  - links outcomes to interventions via `intervention_theme_id`
  - causal mechanism fields belong at outcome granularity (intervention–outcome), not only intervention level

Operational note: apply the relevant migration(s) before expecting new synthesis fields to appear in stored summaries.

## API and frontend usage

### Search wizard: target inner setting

The search wizard can suggest and collect a user’s **inner setting** (delivery environment). This becomes part of the project `search_query` and is consumed by Tier 2 transferability scoring.

### Synthesis summary payload

The API should expose (and the frontend can display):

- outcome verdicts (label + description)
- discord flags (contested evidence)
- magnitude estimate + confidence
- causal mechanism at outcome level (computed in Tier 2; may be refined further in Tier 4)
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

## Notes on legacy scores

Some parts of the UI still show legacy scalar scores (e.g., average impact/evidence star ratings). These should not be treated as the Impact Profile; the Impact Profile is the outcome-level vector described above.


