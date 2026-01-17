# Evidence Strength Assessment Specification

## Overview

This document specifies the methodology for assessing and displaying evidence strength in Policy Atlas. The system assigns star ratings to both individual documents and aggregated intervention themes based on evidence type classification.

**Scope:** This methodology applies to **new projects only**. Existing projects retain the previous averaging methodology.

---

## 1. Evidence Typology and Scoring

Individual documents are classified into evidence types with associated scores (0-5):

| Score | Evidence Type | Definition | Examples |
|------:|---------------|------------|----------|
| **5** | Systematic Review / Meta-Analysis | Collects and critically appraises all relevant studies on a topic, often combining results statistically via meta-analysis. Typically prioritises high-quality evidence such as RCTs. | Cochrane reviews; Blueprint systematic reviews; PRISMA-based papers |
| **4** | RCTs and Quasi-Experimental Studies | RCTs randomly assign participants to treatment and control groups. Quasi-experimental studies estimate causal impacts without random assignment. | Individual RCTs; treatment vs control studies; difference-in-differences; regression discontinuity |
| **3** | Observational Research Studies | Research without controlled assignment to exposure or intervention. | Cohort; case-control; cross-sectional; longitudinal studies |
| **2** | Modelling & Simulation | Mathematical, computational, or conceptual models used for forecasting or scenario analysis. | Economic models; OECD modelling reports; forecasts |
| **2** | Policy Syntheses & Guidance | Synthesises existing evidence to provide recommendations rather than new empirical findings. | Government white papers; think tank reports |
| **2** | Qualitative & Contextual Evidence | Explores experiences, perceptions, and real-world implementation contexts. | Interviews; focus groups; case studies; parliamentary evidence |
| **1** | Expert Opinion & Commentary | Based on professional judgement rather than systematic empirical research. | Editorials; opinion pieces; essays |
| **0** | Unknown / Insufficient Information | Insufficient detail to classify evidence type. | Title-only or sparse records |

**Note:** "Other (Non-evidence Documents)" (bills, press releases, statistical bulletins) are filtered out upstream and do not appear in the evidence assessment workflow.

---

## 2. Classification Requirements

### 2.1 Confidence Threshold

Only classifications meeting a **minimum confidence threshold of 0.5 (50%)** are included in star rating calculations.

- Documents below this threshold are excluded from evidence type counts
- These documents **are** counted in the total document count (affects density calculations)

### 2.2 Study Counting

- Each document is treated as **one study** for counting purposes
- Existing deduplication processes apply upstream
- No additional study-level deduplication is performed during aggregation

### 2.3 No User Overrides

Classification is system-determined. Users cannot override or correct evidence type classifications.

---

## 3. Intervention Theme Star Rating Rules

When aggregating evidence across an intervention theme, rate by the **strongest level of causal evidence present** (do not average scores).

### 3.1 Base Rating Rules

| Rating | Criteria |
|--------|----------|
| 5 stars | Theme includes **at least 1** Systematic Review or Meta-Analysis |
| 4 stars | Theme includes **at least 1** RCT or quasi-experimental study |
| 3 stars | Theme includes **at least 1** observational study |
| 2 stars | Evidence limited to modelling, qualitative, or policy studies **OR** only a single observational study |
| 1 star | Theme contains **expert opinion only** |
| 0 stars | No relevant evidence available or all evidence below confidence threshold |

### 3.2 Cap Rules

Three cap rules may reduce the base rating. When multiple caps could apply, the **strictest cap wins** (caps do not compound).

#### Single-Study Cap

If the rating is driven by **exactly one unique study** at that evidence level:

| Base Rating | Capped To | Condition |
|-------------|-----------|-----------|
| 5 stars | 4 stars | Single SR/MA with no supporting primary studies |
| 4 stars | 3 stars | Single RCT or quasi-experimental study only |
| 3 stars | 2 stars | Single observational study only |

#### Density Cap

If an intervention cluster contains **fewer than 2.5% of total project documents**:

- Cap at **3 stars maximum**
- This cap applies **even if** the cluster contains a Systematic Review or Meta-Analysis
- A sparse cluster with a single SR/MA is capped at **3 stars** (strictest cap wins)

### 3.3 Cap Application Example

**Scenario:** Theme has 1 RCT, and only 3 documents total in a 200-document project (1.5% density)

- Base rating: 4 stars (has RCT)
- Single-study cap: Would reduce to 3 stars
- Density cap: Would reduce to 3 stars (< 2.5%)
- **Final rating: 3 stars** (strictest cap, both happen to be equal)

**Scenario:** Theme has 1 SR/MA, and only 4 documents total in a 200-document project (2% density)

- Base rating: 5 stars (has SR/MA)
- Single-study cap: Would reduce to 4 stars
- Density cap: Would reduce to 3 stars (< 2.5%)
- **Final rating: 3 stars** (density cap is strictest)

---

## 4. Display Specifications

### 4.1 Documents Tab

**Individual Document Display:**

- Show **0-5 stars** matching the document's evidence type score
- Tooltip displays **score only** (numeric value)
- Documents classified as "Unknown" (Score 0) display 0 stars

### 4.2 Interventions Tab

**Aggregated Theme Display:**

- Show **0-5 star rating** for the intervention theme
- **Evidence mix always visible** alongside the star rating, use colour scheme of Evidence Category already implemented within Documents table for tags of Evidence mix.
- Full breakdown of all evidence types present

**Evidence Mix Format:**
```
Systematic Reviews (3), RCTs (5), Observational (8), Modelling (2), Policy Syntheses (4), Qualitative (12), Opinion (1)
```

**Sorting:**

- Users can **sort** intervention themes by star rating
- No filtering by star rating (sort only)

**Cap Reason Display:**

- When a cap reduces the rating, display a **user-friendly message**
- Show only the **applied cap** (the strictest one), not all caps that could have applied

| Cap Type | User-Friendly Message |
|----------|----------------------|
| Single SR/MA | "Limited by single systematic review" |
| Single RCT | "Limited by single experimental study" |
| Single Observational | "Limited by single observational study" |
| Density | "Limited by small evidence base" |

### 4.3 Empty State

When an intervention theme has 0 documents meeting the confidence threshold:

- Display **0 stars** (all empty)
- Show message: **"No qualifying evidence"**

---

## 5. Technical Implementation

### 5.1 Computation

- Aggregation follows the existing pattern (computed during data processing)
- Replace averaging methodology with "strongest evidence + caps" methodology

### 5.2 Priority

1. Backend aggregation logic
2. UI updates (Documents tab, Interventions tab)

### 5.3 Logging

Implement **basic logging** when caps are applied:

- Log intervention theme ID
- Log base rating before cap
- Log final rating after cap
- Log which cap was applied

### 5.4 Rollout

- **New projects only** - apply new methodology
- **Existing projects** - retain previous averaging methodology
- **Full replacement** - no need to preserve old averaging code; git history is sufficient

---

## 6. Methodology Limitations

The following limitations should be documented and communicated to users:

### 6.1 Classification Accuracy

The LLM/algorithm-based classification may misclassify evidence types. Users should not treat classifications as definitive without reviewing the underlying documents.

### 6.2 Study Quality Not Assessed

All studies of the same type are weighted equally. A well-designed, adequately powered RCT is treated the same as a small pilot RCT with methodological limitations. The star rating reflects evidence **type**, not evidence **quality**.

### 6.3 Recency Not Factored

Older studies are weighted the same as recent ones. A 20-year-old RCT contributes equally to the rating as a study published last year. Users should consider whether evidence is current for their policy context.

### 6.4 Geographic Context Ignored

Evidence from different geographic, cultural, or policy contexts is treated equivalently. A study conducted in a different country or healthcare system may not directly apply to the user's context.

### 6.5 Single High-Quality Studies May Be Underrated

The single-study cap rules may underrate themes supported by a single but exceptionally rigorous study. A landmark, well-designed RCT will still be capped at 3 stars if it's the only experimental evidence for that theme.

---

## 7. Data Schema Reference

### 7.1 Document Evidence Assessment

In terms of classification_confidence, we actually already have an evidence_category and evidence_category_confidence field (those are approximately the names. Double check this.)
```
{
  "document_id": string,
  "evidence_type": string,  // One of the 8 types from typology
  "evidence_score": int,    // 0-5
  "classification_confidence": float,  // 0.0-1.0
  "meets_threshold": boolean  // true if confidence >= 0.6
}
```

### 7.2 Intervention Theme Assessment
Double check this to make sure it agrees with schemas we already have and that there isn't any overlap.
```
{
  "theme_id": string,
  "base_rating": int,       // 0-5 before caps
  "final_rating": int,      // 0-5 after caps
  "cap_applied": string | null,  // "single_srma" | "single_rct" | "single_obs" | "density" | null
  "cap_reason_display": string | null,  // User-friendly message
  "document_count": int,    // Total docs in theme meeting threshold
  "project_total": int,     // Total docs in project
  "density_percentage": float,  // document_count / project_total
  "evidence_mix": {
    "systematic_review": int,
    "rct_quasi_experimental": int,
    "observational": int,
    "modelling": int,
    "policy_synthesis": int,
    "qualitative": int,
    "expert_opinion": int,
    "unknown": int
  }
}
```

---

## 8. Algorithm Pseudocode

Use evidence_category for counting. 
```python
def calculate_theme_rating(theme_documents, project_total):
    # Filter to documents meeting confidence threshold
    qualifying_docs = [d for d in theme_documents if d.confidence >= 0.6]

    if not qualifying_docs:
        return Rating(stars=0, cap=None, message="No qualifying evidence")

    # Count by evidence type
    counts = count_by_evidence_type(qualifying_docs)

    # Determine base rating (strongest evidence present)
    if counts['systematic_review'] >= 1:
        base_rating = 5
    elif counts['rct_quasi_experimental'] >= 1:
        base_rating = 4
    elif counts['observational'] >= 1:
        base_rating = 3
    elif counts['modelling'] + counts['policy_synthesis'] + counts['qualitative'] >= 1:
        base_rating = 2
    elif counts['expert_opinion'] >= 1:
        base_rating = 1
    else:
        base_rating = 0

    # Calculate potential caps
    caps = []

    # Single-study caps
    if base_rating == 5 and counts['systematic_review'] == 1:
        caps.append(('single_srma', 4, "Limited by single systematic review"))
    if base_rating == 4 and counts['rct_quasi_experimental'] == 1:
        caps.append(('single_rct', 3, "Limited by single experimental study"))
    if base_rating == 3 and counts['observational'] == 1:
        caps.append(('single_obs', 2, "Limited by single observational study"))

    # Density cap
    density = len(qualifying_docs) / project_total
    if density < 0.025:  # < 2.5%
        caps.append(('density', 3, "Limited by small evidence base"))

    # Apply strictest cap
    final_rating = base_rating
    applied_cap = None
    cap_message = None

    for cap_type, cap_value, message in caps:
        if cap_value < final_rating:
            final_rating = cap_value
            applied_cap = cap_type
            cap_message = message

    return Rating(
        stars=final_rating,
        cap=applied_cap,
        message=cap_message,
        evidence_mix=counts
    )
```

---

## Appendix: Star Rating Visual Reference

| Rating | Display | Meaning |
|--------|---------|---------|
| 5 stars | :star::star::star::star::star: | Systematic review/meta-analysis evidence |
| 4 stars | :star::star::star::star: | RCT/quasi-experimental evidence |
| 3 stars | :star::star::star: | Observational study evidence |
| 2 stars | :star::star: | Modelling, qualitative, or policy evidence |
| 1 star | :star: | Expert opinion only |
| 0 stars | (empty) | No qualifying evidence |
