# Impact assessment methodology

Impact assessment answers five questions per intervention–outcome pair:

- **Does it work?** (directional consensus via verdict labels)
- **How much does it work?** (calibrated magnitude estimate)
- **How strong is the causal claim?** (causal mechanism — attribution / contribution / correlation)
- **Will it work here?** (transferability / context fit)
- **What could go wrong?** (risk themes and harm warnings)

---

## Core principle: impact is a structured profile

The primary output is a structured **Impact Profile** — a multi-dimensional
vector of verdict, magnitude, causality, transferability, and risk — assembled
across two tiers:

- **Tier 1 ("Reader")**: document-level, factual extraction.
- **Tier 2 ("Judge")**: cross-document synthesis using evidence-quality
  weighting, including calibrated magnitude thresholds.

### Scalar impact scores (secondary output)

In addition to the Impact Profile, the system computes **scalar impact scores**
at both document and intervention level.  These scores exist primarily for
ranking and sorting in the UI, and should not be treated as the full assessment.

- **Document-level impact score** (1.0–5.0): computed in Tier 1 from signed
  magnitude, outcome similarity, causal weights, and transferability; may be
  **overwritten** by Tier 2 calibration (see §Tier 2 calibration pass below).
- **Intervention-level impact score** (1.0–5.0): aggregated from
  document-level scores using a maximum-based strategy with evidence caps and
  a proportional discord penalty (see §Intervention-level impact score).

Both scores use labels: Very high (≥ 4.5), High (≥ 3.5), Moderate (≥ 2.5),
Low (≥ 1.5), Very low (< 1.5).

---

## Evidence quality score

Each document receives an **evidence quality score** on an integer **0–5**
scale.  This score is the weighting factor used throughout synthesis.

| Score | Typical category | Description |
|-------|-----------------|-------------|
| 5 | Systematic review / meta-analysis | Highest methodological tier |
| 4 | RCT / quasi-experimental | Strong causal designs |
| 3 | Observational research | Non-randomised evidence |
| 2 | Modelling, policy synthesis, qualitative | Lower causal certainty |
| 1 | Expert opinion / commentary | Minimal empirical backing |
| 0 | No qualifying evidence or unknown | Cannot be scored |

### Score provenance

Evidence quality is **preferentially loaded from the stored conclusion**
(`extraction_results.conclusion.evidence_strength.stars`), which is set during
Tier 1 extraction.  If that value is absent, Tier 2 **recomputes** it from the
document's evidence category using `calculate_document_evidence_score()` in
`analysis/evidence/strength.py`.  This recomputation applies a **sample-size
penalty** (−1 star) when the evidence category is causal (RCT or
observational) and the known sample size is below 100.

**Implementation**: `data_loading.py → get_or_calculate_document_evidence()`.

---

## Inputs and outputs

### Inputs

- **Documents** (papers / reports) and associated metadata.
- **Tier 1 extractions** (atomic signals per document).
- **Evidence quality scores** (0–5) per document.
- **User target context** (from the search wizard / project `search_query`):
  - population
  - inner setting (delivery environment)
  - geography — although collected, **transferability geography is hard-fixed
    to UK** in the current implementation (see §Transferability).
  - outcomes of interest
  - implementation constraints (optional): cost, staffing, implementation
    complexity

### Outputs

- **Outcome-level impact profile** (one per intervention–outcome pair):
  - verdict label + description
  - discord/contested flag + reason (where applicable)
  - predicted magnitude + structured magnitude detail (direction, bucket
    counts, source/measurement counts, dominant scale, thresholds)
  - causal mechanism (attribution / contribution / correlation) + structured
    quality-weighted support counts
  - per-outcome **consensus meter** (directional evidence counts) for the UI
- **Intervention-level outputs**:
  - **Context Fit** rating + breakdown (inner setting, population, geography)
  - **Implementation requirements** rating (Low / Medium / High / Unknown)
    derived from evidence levels
  - Implementation dimensions always show **evidence levels**
    (low / moderate / high / unknown)
  - When user tolerances are provided, show an **exceeds tolerance** flag per
    dimension
  - LLM-based explanations per dimension in breakdown notes
  - **Impact summary** — LLM-generated natural-language synthesis
  - **Scalar impact score** + label + breakdown (secondary ranking output)
- **Risk profile**:
  - clustered risk themes
  - harm warning flag (boolean; see §Harm warning)
  - primary + secondary linkage between risk themes and intervention themes

---

## Tier 1 ("Reader"): atomic extraction per document

Tier 1 runs a multi-stage extraction pipeline:

`extract_issues → extract_interventions → extract_mappings → extract_results → extract_conclusions`

### Results (outcomes per intervention)

Tier 1 extracts factual outcome signals per intervention:

- **effect_direction**: `increase | decrease | null | mixed | inconclusive`
- **effect_size_type**: raw metric label (e.g., "Cohen's d", "OR")
- **effect_size**: raw value (e.g., "0.3 SD", "15%", "OR 0.85")
- **causality_claim**: `attribution | contribution | correlation`
- **negative_impact_flag**: boolean (true if harm / adverse effects are indicated)
- **is_primary**: boolean (true for primary outcomes the study was designed to measure)
- **is_beneficial**: boolean (true if the outcome change benefits the population)
- **is_prevalence_only**: boolean (true for descriptive snapshots with no intervention comparison)
- **magnitude_estimate**: `substantial | large | moderate | marginal | unknown`
  — an initial semantic bucket assigned at extraction time.  Tier 2 may
  overwrite this with calibrated thresholds.
- supporting quote(s)

**Note on magnitude**: Tier 1 assigns a preliminary `magnitude_estimate` based
on the LLM's interpretation of the effect size.  Cross-document calibration
happens in Tier 2, where outcome-specific thresholds are generated and applied.
If calibrated thresholds are available, they take precedence over the Tier 1
bucket.

### Interventions (implementation profile)

Tier 1 extracts the intervention plus CFIR-inspired delivery characteristics:

- **country** (outer setting proxy)
- **population_intervened** (beneficiary proxy)
- **population_demographics**
- **sample_size**
- **inner_setting** (e.g., School, Clinical/Hospital, Prison, Community) — uses
  the recipient-facing setting, not the policy-making body
- **cost_level** + justification (High / Moderate / Low / null)
- **staffing_level** + justification (High / Moderate / Low / null)
- **implementation_complexity_level** + justification (High / Moderate / Low / null)
- supporting quote(s)

### Conclusions (document-level risk and quality assessment)

Conclusions include:

- **evidence_strength** — a `stars` rating (0–5) plus justification and an
  optional `evidence_gap` note
- **risk_assessment**:
  - `risks_identified`: list of intervention-related risks (harms, adverse
    effects, implementation challenges) — does **not** include the underlying
    problem the intervention addresses
  - `unintended_consequences_detected`: boolean
- **study_context** — fallback document-level context (country, population,
  inner_setting, cost/staffing/complexity levels) used when intervention-level
  data is sparse

---

## Tier 2 ("Judge"): cross-document synthesis

Tier 2 consumes Tier 1 extractions and produces theme-level synthesis with
evidence-quality weighted logic.

### High-level workflow

1. **Load** (`data_loading.py`)
   - Load raw extractions and document evidence-quality scores.
   - If a stored evidence strength score exists it is used; otherwise it is
     recomputed from evidence category (with sample-size penalty).
   - Load **target context** (inner setting, population, outcomes, geography,
     implementation constraints) from project `search_query`.

2. **Canonical concept creation** (`data_loading.py`)
   - Create canonical concepts for clustering from each extraction type.
   - Extract **risk concepts** from:
     - conclusion `risk_assessment.risks_identified`
     - results marked with `negative_impact_flag=true`

3. **Theme discovery** — parallel for each branch (`theme_discovery.py`)
   - issue themes
   - intervention themes
   - outcome themes (semantic equivalence clustering)
   - risk themes

4. **Aggregation** (`aggregation.py`)
   - Compute **quality-weighted directional counts** for outcomes:
     - Each result extraction contributes `evidence_score / 5` to its
       directional bucket (positive, negative, or null).
     - Buckets are rounded up (`math.ceil`) to whole numbers for display.
     - **Counting unit**: individual result extractions, not documents.  A
       single high-quality document with multiple extracted results contributes
       multiple weighted increments. (TODO: consider changing to document level counting instead of result level)
   - **Handling of mixed/inconclusive directions**: results with
     `effect_direction` of `mixed` or `inconclusive` do not increment any
     bucket (equivalent to "no data" for aggregation purposes). (TODO: handle these)
   - Select representative effect sizes (quality-prioritised, numeric-biased,
     deduplicated).
   - Build theme→extraction ID and theme→document UUID mappings.

5. **Impact synthesis (enrichment)** (`impact_synthesis.py`)
   - Verdict label + description (see §Verdict labels)
   - Discord flag + reason (see §Discord / contested evidence)
   - Predicted magnitude + structured `MagnitudeDetail` (see §Magnitude)
   - Causal mechanism + `CausalityDetail` (see §Causal mechanism)
   - Transferability rating + `TransferabilityBreakdown` (see §Transferability)
   - Risk themes linked to interventions + harm warning flag
   - LLM-generated `impact_summary` per intervention
   - Scalar impact score per intervention

---

## Verdict labels

Verdicts communicate **direction** and **evidence strength** (not magnitude or
causality).  Direction uses **positive/negative** terminology (not
increase/decrease), based on the `is_beneficial` flag — the frontend interprets direction in outcome context
(e.g., a decrease in obesity counts as a positive outcome).

### Canonical verdict set

```
VerdictType = Literal[
    "well_evidenced_positive",
    "well_evidenced_negative",
    "evidenced_positive",
    "evidenced_negative",
    "suggested_positive",
    "suggested_negative",
    "contested",
    "no_effect",
    "insufficient_evidence",
    "probable_contribution",
]
```

### Verdict thresholds

Verdicts are determined by the quality-weighted directional counts using the
following thresholds:

| Condition | Verdict |
|-----------|---------|
| Total weight < **3** | `insufficient_evidence` |
| min(pos, neg) / max(pos, neg) > **0.4** | `contested` |
| null > pos AND null > neg | `no_effect` |
| pos > neg AND pos > **15** | `well_evidenced_positive` |
| pos > neg AND pos > **8** | `evidenced_positive` |
| pos > neg | `suggested_positive` |
| neg > pos (same tiers) | `…_negative` equivalents |
| pos == neg | `insufficient_evidence` |

### Contribution fallback

If a verdict would be `well_evidenced_positive` or `well_evidenced_negative`
but **no attribution-quality evidence** exists for the outcome (i.e., no result
extraction has `causality_claim == "attribution"`), the verdict is downgraded
to `probable_contribution` to avoid overstating causal certainty.

**Implementation**: `impact_synthesis.py → determine_verdict()`.

---

## Magnitude

### Hybrid magnitude estimation

Magnitude is estimated using a two-stage approach:

1. **Static scale detection**: the effect size type is matched against known
   scales with built-in thresholds:

   | Scale | Marginal | Moderate | Large | Substantial |
   |-------|----------|----------|-------|-------------|
   | Cohen's d / SMD | < 0.2 | 0.2–0.5 | 0.5–0.8 | > 0.8 |
   | OR / RR | < 1.2 | 1.2–1.5 | 1.5–2.0 | > 2.0 |
   | Percentage | < 5% | 5–15% | 15–30% | > 30% |

2. **Dynamic LLM-calibrated thresholds**: for each outcome theme, an LLM
   (default: GPT-4o-mini) examines all extracted effect sizes for that outcome
   across interventions and generates **domain-appropriate thresholds**.  These
   are cached per outcome and take precedence over the static scales when
   available.

### Magnitude aggregation

Within an outcome–intervention pair:

- Only effects aligned with the dominant direction (or all, if `contested`)
  are counted.
- Each effect contributes its calibrated magnitude bucket weighted by evidence
  quality.
- When the highest-weighted bucket is tied, the **lower** (more conservative)
  bucket is chosen — the "prudence check".

### Magnitude detail structure

The `MagnitudeDetail` object stores:

- `direction`: `increase | decrease | contested`
- `bucket_counts`: quality-weighted counts per magnitude bucket
- `source_count` / `total_sources` / `measurement_count`
- `dominant_scale`: the most common effect size type
- `thresholds`: human-readable threshold text for tooltips

### Semantic magnitude type

```
SemanticMagnitudeType = Literal[
    "transformational", "substantial", "large", "moderate", "marginal", "unknown"
]
```

**Implementation**: `impact_synthesis.py → compute_magnitude_hybrid()`,
`generate_dynamic_thresholds()`.

---

## Causal mechanism

The primary causal mechanism is determined per outcome–intervention pair from
result-level `causality_claim` fields, weighted by evidence quality score:

- Each result extraction contributes its evidence quality score to the
  corresponding claim bucket (attribution / contribution / correlation).
- The mechanism with the highest cumulative weight is the primary.

The `CausalityDetail` object stores the quality-weighted counts for each claim
type.

**Implementation**: `impact_synthesis.py → compute_causal_mechanism()`.

---

## Transferability

Transferability is assessed at the **intervention** level across six dimensions
split into two groups:

### Context dimensions (LLM-assessed semantic similarity)

| Dimension | Target source | Evidence source |
|-----------|--------------|-----------------|
| Inner setting | `search_query.inner_setting` | Extraction `inner_setting` |
| Population | `search_query.population` | Extraction `population_intervened` |
| Geography | **Hard-fixed to `["UK"]`** | Extraction `country` (with fallback to `doc_metadata.source_country`) |

**Geography note**: although the search wizard collects user-specified
geography and this value is loaded into Tier 2 state, the transferability
computation currently **ignores** it and uses `DEFAULT_TARGET_GEOGRAPHY =
["UK"]`.  This is by design for Policy Atlas's UK policymaker audience.

Each context dimension is assessed using an **LLM semantic similarity call**
(default model: GPT-4o-mini) that compares target and evidence values and
returns one of:

- `match` → 1.0
- `similar` → 0.85
- `comparable` → 0.70
- `partial` → 0.40
- `mismatch` → 0.0
- `unknown` → excluded from average
- `not_compared` → returned when no target is specified; excluded from average

The **Context Fit rating** is the headline transferability output and is
computed from the average of the three context dimension scores:

| Average score | Rating |
|---------------|--------|
| ≥ 0.85 | Excellent Fit |
| ≥ 0.70 | Good Fit |
| ≥ 0.50 | Moderate Fit |
| ≥ 0.30 | Limited Fit |
| < 0.30 or any mismatch | Poor Fit |
| Fewer than 2 valid scores | Unknown |

### Implementation dimensions (ordinal evidence inference)

| Dimension | Evidence source | Aggregation |
|-----------|----------------|-------------|
| Cost | `cost_level` | Most-common level across extractions |
| Staffing | `staffing_level` | Most-common level across extractions |
| Implementation complexity | `implementation_complexity_level` | Most-common level across extractions |

These dimensions are **not** weighted by evidence quality — they use simple
mode (most-common) aggregation.

Each dimension produces:

- **Evidence level**: low / moderate / high / unknown
- **Exceeds tolerance flag**: true when evidence level > user-specified
  tolerance (only when user constraints are provided)
- **LLM explanation**: a one-sentence note contextualising the evidence or
  tolerance alignment

The **Implementation requirements rating** is the maximum of the three
evidence levels: Low / Medium / High / Unknown.

### TransferabilityBreakdown schema

```
TransferabilityBreakdown:
    inner_setting: str          # match level
    population: str             # match level
    geography: str              # match level
    notes: Dict[str, str]       # per-dimension LLM explanations
    data_availability: Dict     # e.g., "3 of 5" extractions have data
    context_fit_rating: str     # headline rating
    implementation_requirements_rating: str
    implementation_constraints_specified: bool
    implementation_evidence: Dict[str, str]
    implementation_constraints: Dict[str, str]
    implementation_exceeds_tolerance: Dict[str, bool]
```

**Implementation**: `impact_synthesis.py → compute_transferability()`,
`assess_transferability_dimension()`.

---

## Harm warning

Harm warnings are computed at the **risk theme** level using conclusion-level
risk assessment data.

### Tier 2 harm warning (cross-document)

The function examines documents linked to a risk theme and checks whether
>20% of **high-quality** documents (evidence score ≥ 4) have
`unintended_consequences_detected == true` in their conclusion risk assessment.

The output is a **boolean flag only** (`has_harm_warning`).  A human-readable
reason is not generated at synthesis time.

**Note**: the Tier 2 harm warning uses conclusion-level
`unintended_consequences_detected`, not the result-level
`negative_impact_flag`.  Result-level negative flags are used during risk
*concept* creation (i.e., they feed into the risk theme clustering pipeline)
but do not directly trigger the harm warning.

### Document-level harm warning (Tier 1 utility)

A separate utility in `analysis/scoring.py → compute_harm_warning()` computes
a document-level `(flag, reason)` tuple from `has_negative_impact` and number
of `risks_identified`.  This is used during Tier 1 storage and is distinct from
the Tier 2 cross-document harm warning.

**Implementation**: `impact_synthesis.py → compute_harm_warning()` (Tier 2),
`analysis/scoring.py → compute_harm_warning()` (Tier 1).

---

## Null vs "no data" vs mixed/inconclusive

| Direction value | Treatment in aggregation |
|-----------------|------------------------|
| `null` / `none` / `no effect` | Counts as evidence in the **null** bucket (quality-weighted) |
| `increase` or `is_beneficial=true` | Counts in the **positive** bucket |
| `decrease` or `is_beneficial=false` | Counts in the **negative** bucket |
| `mixed` / `inconclusive` | **Does not increment any bucket** — treated as absent evidence |
| Absent / not extracted | Does not contribute to any bucket |

---

## Discord / contested evidence

Discord is detected by comparing quality-weighted positive and negative counts:

```
ratio = min(positive, negative) / max(positive, negative)
if ratio > 0.4:
    verdict = "contested"
    discord_reason = f"Evidence split: {positive}↑ vs {negative}↓"
```

Discord detection runs **before** strength-tier assignment.  If evidence is
contested, no strength tier is applied.

---

## Scalar impact scores

### Document-level transferability (numeric score)

Before the document impact score can be computed, a **numeric transferability
score** (0.2–1.0) is calculated per document.  This is a Tier 1 computation
(`analysis/scoring.py → compute_document_transferability()`) that runs at
extraction-storage time, distinct from the Tier 2 categorical Context Fit
rating described above.

#### Inputs

| Input | Source |
|-------|--------|
| `doc_context` | Aggregated from all interventions extracted for the document: `country`, `population_intervened`, `inner_setting` |
| `target_context` | From project `search_query`: geography (hard-fixed to `["UK"]`), population, inner setting |
| `implementation_evidence` | Aggregated `cost_level`, `staffing_level`, `implementation_complexity_level` from extractions |
| `user_constraints` | Optional tolerance limits from `search_query.implementation_constraints` |

#### Context fit (continuous)

Each of the three context dimensions (geography, population, inner_setting) is
assessed via the same LLM semantic similarity call as Tier 2 (`assess_dimension()`),
returning a match level that maps to a numeric score.

**Document-level match scores** (note: these differ from Tier 2):

| Match level | Score |
|-------------|-------|
| `match` | 1.0 |
| `similar` | 0.85 |
| `comparable` | 0.7 |
| `partial` | 0.4 |
| `mismatch` | 0.15 |
| `unknown` | 0.5 |

Key differences from the Tier 2 transferability match scores:

- `mismatch` → **0.15** (not 0.0) — avoids completely zeroing a document score
  on a single dimension mismatch.
- `unknown` → **0.5** (not excluded) — contributes a neutral value rather than
  being dropped from the average.

`context_fit = mean(valid_scores)` (all three are always included since
`unknown` has a numeric value).  Falls back to 0.5 if no scores are valid.

#### Constraint penalty (multiplicative)

For each implementation dimension (cost, staffing, implementation_complexity):

- Normalise both the user tolerance and the evidence level to `low` / `moderate` / `high`.
- If the evidence level **exceeds** the user tolerance (e.g., evidence is
  "high" but user tolerance is "moderate"), apply a **0.5× penalty** per
  exceeding dimension.

The penalties stack multiplicatively (e.g., two exceeding dimensions →
0.5 × 0.5 = 0.25).

#### Final score

```
transferability = clamp(context_fit × constraint_penalty, 0.2, 1.0)
```

The floor of 0.2 ensures even heavily penalised documents still contribute
a non-trivial score rather than collapsing to zero.

#### Breakdown

The returned breakdown dict includes: `context_fit`, per-dimension match
levels, `constraints_provided`, `constraint_levels`, `implementation_evidence`,
`extracted_context`, and `exceeds_constraints`.

**Implementation**: `analysis/scoring.py → compute_document_transferability()`,
`analysis/storage.py → _compute_document_scores()`.

---

### Document-level impact score

Computed by `analysis/scoring.py → compute_document_impact_score()`.  Takes the
document-level transferability score (above) as an input.

1. **Filter outcomes**: remove prevalence-only results, then keep only primary
   outcomes.  If no primary outcomes remain, the document receives no score.

2. **Per-outcome signals** — for each included primary outcome, three values
   are computed:

   - **Signed magnitude** (`signed_mag`, range −1.0 to +1.0): looked up from
     the `MAGNITUDE_NORMALISED` table below, then negated when the outcome is
     harmful (`is_beneficial=false`).  For directions of `null`, `mixed`, or
     `inconclusive` the signed magnitude is 0.0.

     | Magnitude bucket | Normalised value |
     |-----------------|-----------------|
     | `substantial` | 1.0 |
     | `transformational` | 1.0 |
     | `large` | 0.75 |
     | `moderate` | 0.5 |
     | `marginal` | 0.25 |
     | `unknown` | 0.25 |

   - **Outcome similarity** (`similarity`, 0.0–1.0): how relevant this
     extracted outcome is to the user's target outcomes, assessed via an LLM
     call.  If the user did not specify target outcomes, similarity defaults
     to 1.0.  Outcomes with similarity < 0.5 are **excluded** from the score
     entirely.

   - **Causal weight** (`causal_w`): reflects confidence in the causal claim.

     | Causality claim | Weight |
     |----------------|--------|
     | `attribution` | 1.0 |
     | `contribution` | 0.9 |
     | `correlation` | 0.7 |
     | missing / unknown | 0.9 |

3. **Net magnitude** — a weighted average of signed magnitudes across all
   included outcomes.  The weight for each outcome is its
   `similarity × causal_w`:

   ```
   For each outcome i:
       weight_i      = similarity_i × causal_w_i
       contribution_i = signed_mag_i × weight_i

   net_magnitude = Σ contribution_i  /  Σ weight_i
   ```

   This is a standard weighted mean.  Outcomes that are more relevant to the
   user's targets (high similarity) and backed by stronger causal designs
   (high causal weight) contribute proportionally more to the overall
   magnitude.  The result ranges from −1.0 (all outcomes harmful at maximum
   magnitude) to +1.0 (all outcomes beneficial at maximum magnitude).

4. **Base score**: centres the net magnitude on a 1–5 scale:

   ```
   base_score = 2.5 + (net_magnitude × 2.5)
   ```

   A net magnitude of 0 → base score of 2.5 (neutral).  Fully beneficial
   → 5.0.  Fully harmful → 0.0.

5. **Transferability dampening**: reduces the score proportionally to how
   transferable the evidence is to the user's context:

   ```
   dampened = base_score × transferability^0.3
   ```

   The exponent of 0.3 means the penalty is mild — a transferability of 0.5
   only reduces the score by ~19%.  This avoids over-penalising documents
   from different contexts while still rewarding high transferability.

6. **Clamp** to 1.0–5.0.

### Tier 2 calibration pass

After Tier 2 generates dynamic magnitude thresholds, document-level impact
scores are **recalculated** using the calibrated magnitudes
(`rescore_document_scores_with_calibration()`).  This ensures document scores
are consistent with the synthesis-level magnitude buckets.  The recalculated
scores are written back to `doc_scores` and persisted to `analysis_documents`.

### Intervention-level impact score

Computed by `analysis/scoring.py → compute_intervention_impact_score()`:

1. Exclude floor-one documents (those with score=1.0 and labels like "No
   Outcomes" or notes indicating no usable outcomes).
2. Select the **best-evidence document** (highest evidence score; ties broken
   by highest impact score).
3. Apply **moderate caps** on the base score:

   | Condition | Cap |
   |-----------|-----|
   | Single contributing study | 4.0 |
   | ≤ 3 contributing studies | 4.3 |
   | Best evidence score < 3 | 3.0 |
   | Best evidence score < 4 | 3.5 |
   | Best causality weight < 0.6 | 3.5 |

4. Apply **discord penalty**: proportional to the quality-weighted fraction of
   negative-direction documents (capped at 4.0 before penalty; penalty =
   neg_proportion × 1.0).
5. Clamp to 1.0–5.0.

The aggregation method is recorded as `"maximum"` in the breakdown.

**Implementation**: `analysis/scoring.py → compute_intervention_impact_score()`,
`impact_synthesis.py → build_intervention()`.

---

## Impact summary text (intervention-level)

An LLM (default: GPT-4o-mini) generates a 2–3 sentence `impact_summary` per
intervention.  The prompt instructs:

- Directly state the intervention's effect on user-specified outcomes
- Note the evidence strength tier
- Flag any contested or insufficient evidence areas
- Reference the research question for focus
- Use plain language suitable for a non-specialist policy audience

**Implementation**: `impact_synthesis.py → generate_impact_summary()`.

---

## Where evidence quality is and is not used

| Component | Quality-weighted? | Notes |
|-----------|:-:|-------|
| Directional bucket counts (pos/neg/null) | ✓ | `evidence_score / 5` per result extraction |
| Magnitude bucket voting | ✓ | Evidence quality used as magnitude bucket weight |
| Causal mechanism voting | ✓ | Evidence quality used as claim weight |
| Discord detection | ✓ | Via quality-weighted directional counts |
| Verdict determination | ✓ | Via quality-weighted counts |
| Transferability context (inner setting / population / geography) | ✗ | LLM semantic similarity; no quality weighting |
| Implementation evidence levels (cost / staffing / complexity) | ✗ | Simple mode (most-common) aggregation |
| Harm warning | Indirect | Only high-quality docs (score ≥ 4) are checked |
| Representative effect size selection | ✓ | Quality-prioritised ranking |

---

## Authoritative code locations

Several modules participate in impact assessment.  This table clarifies which
module is authoritative for each concern:

| Concern | Authoritative module | Notes |
|---------|---------------------|-------|
| Document evidence score | `analysis/evidence/strength.py` | 0–5 scale; Tier 1 stores, Tier 2 recomputes if missing |
| Document impact score | `analysis/scoring.py` | Initial computation; Tier 2 may overwrite via calibration |
| Intervention impact score | `analysis/scoring.py` | Called by Tier 2 `impact_synthesis.py` |
| Outcome similarity | `analysis/scoring.py` | LLM-based outcome relevance scoring |
| Verdict + discord | `synthesis/nodes/impact_synthesis.py` | Tier 2 only |
| Magnitude (calibrated) | `synthesis/nodes/impact_synthesis.py` | Tier 2 dynamic thresholds override Tier 1 buckets |
| Causal mechanism | `synthesis/nodes/impact_synthesis.py` | Tier 2 only |
| Transferability (intervention-level) | `synthesis/nodes/impact_synthesis.py` | Tier 2 implementation; uses LLM for context dimensions |
| Document transferability (Tier 1) | `analysis/scoring.py` | Numeric 0.2–1.0 score; feeds into document impact score dampening; stored on `analysis_documents` |
| Harm warning (cross-document) | `synthesis/nodes/impact_synthesis.py` | Boolean; conclusion-based |
| Harm warning (document-level) | `analysis/scoring.py` | `(flag, reason)` tuple; result/risk-count based |
| Impact summary | `synthesis/nodes/impact_synthesis.py` | LLM-generated |

---

## Persistence (database)

Tier 2 persists synthesis results via `synthesis/logbook.py →
write_run_from_state()`.  The cache uses a version field (currently `version:
4`) and an overwrite strategy for document scores.

### Tables

- **`synthesis_runs`**
  - One row per synthesis execution.  Stores `executive_briefing`,
    `evidence_coverage`, `structured_briefing_data`, and run metadata.
  - Status lifecycle: `running → completed` (or `failed`).
  - Old completed runs are set to `invalidated` before a new run is written.

- **`synthesis_themes`**
  - Stores issue, intervention, and risk themes (distinguished by
    `theme_type`).
  - Intervention themes include: `transferability_rating`,
    `transferability_note`, `transferability_breakdown`, `impact_score`,
    `impact_score_label`, `impact_score_breakdown`, `impact_summary`,
    effect consensus and counts.
  - Risk themes include: `has_harm_warning`, `linked_intervention_theme_id`.

- **`theme_intervention_links`**
  - Many-to-many links between risk themes and intervention themes, with
    `link_strength` (primary / secondary) determined by document overlap.

- **`synthesis_outcome_themes`**
  - One row per intervention–outcome pair.
  - Stores verdict, magnitude, discord, causal mechanism fields.
  - `magnitude_detail` and `causal_mechanism_detail` are stored as JSON.
  - Links to interventions via `intervention_theme_id`.

- **`theme_assignments`** / **`outcome_theme_assignments`**
  - Extraction-to-theme mappings, deduplicated by (theme_id, extraction_id).
  - Outcome assignments also store `calibrated_magnitude` per extraction.

- **`analysis_documents`** (overwrite)
  - After Tier 2 calibration, `impact_score`, `impact_score_label`, and
    `impact_score_breakdown` are written back to each document row.

- **`synthesis_citations`**
  - Citation references for the structured briefing, keyed by citation number.

---

## API and frontend usage

### Search wizard: target context

The search wizard collects:

- **Population** (e.g., "Children under 5") → `search_query.population`
- **Outcomes** (e.g., "BMI reduction") → `search_query.outcome`
- **Inner setting** (e.g., "Schools") → `search_query.inner_setting`
- **Geography** (e.g., "UK") → `search_query.geography` (currently overridden
  by the hard-fixed UK default for transferability)
- **Implementation constraints** → `search_query.implementation_constraints`

### Synthesis summary payload

The API exposes (and the frontend renders):

- Outcome verdicts (label + description)
- Discord flags (contested evidence)
- Magnitude estimate + structured `MagnitudeDetail`
- Causal mechanism at outcome level + `CausalityDetail`
- Context Fit rating + `TransferabilityBreakdown` at intervention level
- Implementation requirements rating + per-dimension evidence/tolerance
- Risk themes + harm warnings linked to interventions
- Scalar impact score + label (for ranking/sorting)
- LLM-generated impact summary per intervention

---