# Impact Score

## Purpose
The impact score is a single-number summary of intervention impact that sits alongside (and stays consistent with) the impact profile. It is designed for quick ranking and comparison, while keeping evidence strength separate.

- Impact score is driven primarily by magnitude and adjusted by transferability.
- Evidence score remains independent and is not multiplied into the impact score.
- Harm warnings are displayed separately and do not directly change the score.

---

## Scale

- Score range: **1.0 to 5.0**
- Rounding: **one decimal place**
- Midpoint: **2.5** represents neutral overall impact

---

## Document-Level Formula

```
DocumentScore = (2.5 + net_magnitude * 2.5) * (T ** 0.4)
```

Where:
- `net_magnitude` is a similarity- and causality-weighted average in **[-1.0, +1.0]**
- `T` is transferability in **[0.2, 1.0]**

Mapping:
- `net_magnitude = -1.0` -> base score 1.0
- `net_magnitude = 0.0` -> base score 2.5
- `net_magnitude = +1.0` -> base score 5.0

Transferability is a dampener rather than a co-equal contributor. The exponent (0.4) softens penalties so low transferability does not fully crush scores.

---

## Net Magnitude

### Magnitude scale (normalised)

```
substantial -> 1.0
large       -> 0.75
moderate    -> 0.5
marginal    -> 0.25
unknown     -> 0.25
```

### Direction and benefit

Signed magnitude is positive for beneficial outcomes and negative for harmful outcomes. The `is_beneficial` flag captures intended direction (for example, BMI decrease can be beneficial).

Null, mixed, and inconclusive outcomes contribute zero magnitude.

### Causality weighting

Each outcome contribution is weighted by causal strength:

```
attribution  -> 1.0
contribution -> 0.9
correlation  -> 0.7
unknown      -> 0.9
```

### Outcome similarity weighting

If the user specifies target outcomes, each outcome is weighted by LLM-assessed similarity (0.0 to 1.0).
Outcomes with similarity below **0.5** are excluded from the score calculation (but retained in the breakdown).

### Net magnitude calculation

```
net_magnitude = sum(signed_mag * similarity * causal_weight) / sum(similarity * causal_weight)
```

Outcomes with unknown magnitude are included with a neutral contribution (0.25) to avoid collapsing
feasibility or early-stage studies to the minimum score. If no outcomes remain after filtering (low similarity
only), the document score is **1.0** with label **"No relevant outcomes"**.

---

## Transferability (T)

Transferability is based on context fit plus implementation constraints.

### Context fit

Assessed per dimension:
- geography
- population
- inner setting

Each dimension is scored (match, similar, comparable, partial, mismatch, unknown) and averaged.

When multiple user contexts are provided, a match is accepted if **any** document context matches **any** user context for that dimension.

Document context can be a list of values aggregated across interventions and (if missing) document-level study context. Geography also falls back to the document's `source_country` when extraction lacks a country.

### Implementation constraints

Constraints are applied as penalties to transferability:

- cost
- staffing
- implementation complexity

If the extracted level exceeds user tolerance for a constraint, transferability is halved for each exceeded constraint.

Final transferability:

```
T = clamp(context_fit * constraint_penalty, min=0.2, max=1.0)
```

---

## Document-Level Breakdown

Each document stores a breakdown for auditability, including:

- outcomes_used
- primary_only
- net_magnitude
- base_score
- transferability
- avg_causal_weight
- constraint_levels (user constraint inputs)
- implementation_evidence (normalised cost/staffing/complexity levels)
- extracted_context (document-level country/population/setting values)
- outcome_breakdown (per outcome):
  - outcome
  - is_primary
  - is_beneficial
  - magnitude
  - signed_magnitude
  - causality_claim
  - causal_weight
  - similarity
  - combined_weight
  - contribution
  - included_in_score
  - excluded_reason

---

## Intervention-Level Aggregation

Document scores are aggregated into an intervention score using a quality-weighted average:

```
InterventionScore = sum(impact_score * evidence_score) / sum(evidence_score)
```

Rules:
- Documents labelled **"No Outcomes"** or **"No relevant outcomes"** are excluded.
- A single document is trusted if **evidence_score ≥ 4**; otherwise apply a **0.85** discount.
- Discord (both positive and negative net magnitudes) is flagged in the breakdown, but does not penalise the score.

The aggregated score is capped in **[1.0, 5.0]** and rounded to one decimal place.

---

## Harm Warnings

Harm warnings are shown separately and do not change the impact score. They are triggered when:

- an outcome has `negative_impact_flag`, or
- there are multiple risks identified

---

## Inputs and Sources

Document-level scoring uses:

- Extraction results (`analysis_documents.extraction_results`)
- Search context (`analysis_projects.search_query`)
  - population, outcome, geography, inner_setting
  - implementation_constraints

Synthesis-level scoring uses:

- Document scores in `analysis_documents`
- Outcome themes and aggregated evidence

---

## Storage Fields

### analysis_documents
- impact_score
- impact_score_label
- impact_score_breakdown
- transferability_score
- transferability_breakdown
- has_harm_warning
- harm_warning_reason

### synthesis_themes
- impact_score
- impact_score_label
- impact_score_breakdown
