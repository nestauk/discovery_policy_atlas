# Relevance Filtering and Evidence Categorization Pipeline

## Overview
This diagram illustrates the two-stage filtering and classification process that occurs after document retrieval but before acquisition. Documents are first assessed for relevance, then categorized by evidence type.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REFERENCES.CSV                                  │
│  (from search/retrieval: doc_id, title, abstract_or_summary, etc.)    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────┐
        │   STEP 1.5: RELEVANCE FILTERING      │
        │   (if relevance_enabled = true)      │
        └──────────────────┬───────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  RELEVANCE SERVICE                                   │
        │  • Model: SCREENING_MODEL (gpt-4.1-mini)           │
        │  • Batch size: 25 documents                          │
        │  • Input: Title + Abstract                          │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  LLM RELEVANCE ASSESSMENT                            │
        │  (Evaluates against search context)                 │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Document 1  │   │  Document 2  │   │  Document N  │
│              │   │              │   │              │
│ Title +      │   │ Title +      │   │ Title +      │
│ Abstract     │   │ Abstract     │   │ Abstract     │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────────────────┐
        │  RELEVANCE EVALUATION CRITERIA                        │
        │  (from RELEVANCE_SYSTEM_PROMPT)                      │
        │                                                       │
        │  1. Research Question Match                           │
        │     • Direct matches and related concepts            │
        │     • Applicable findings, methods, conclusions       │
        │                                                       │
        │  2. Population Interests (if specified)              │
        │     • Prioritize documents addressing populations    │
        │                                                       │
        │  3. Outcome Interests (if specified)               │
        │     • Prioritize documents measuring outcomes        │
        │                                                       │
        │  4. Screening Factors (if specified)                │
        │     • Include/exclude based on criteria              │
        │     • E.g., "studies with children below 5 years"   │
        │                                                       │
        │  5. Geography (if specified)                        │
        │     • Prefer documents from listed countries/regions│
        │     • Exclude others unless transferable            │
        │     • Handle variants (UK = United Kingdom, etc.)    │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  LLM OUTPUT FIELDS                                   │
        │  • is_relevant: bool                                 │
        │  • relevance_confidence: float (0.0-1.0)           │
        │  • relevance_reason: str (1-2 sentences)             │
        │  • top_line: str (15 words max, executive summary)   │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  MERGE RESULTS INTO REFERENCES.CSV                  │
        │  • Add columns: is_relevant, relevance_confidence, │
        │    relevance_reason, top_line                       │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  FILTER: Keep only is_relevant = true               │
        │  (for next step)                                    │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │   STEP 1.75: EVIDENCE CATEGORIZATION                │
        │   (only for relevant documents)                     │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  EVIDENCE CATEGORY SERVICE                           │
        │  • Model: EVIDENCE_CATEGORY_MODEL (gpt-5.2)         │
        │  • Batch size: 25 documents                          │
        │  • Input: Title + Abstract + Metadata               │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  LLM EVIDENCE CLASSIFICATION                        │
        │  (9-category hierarchy by evidence strength)        │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Document 1  │   │  Document 2  │   │  Document N  │
│ (relevant)   │   │ (relevant)    │   │ (relevant)   │
│              │   │              │   │              │
│ Title +      │   │ Title +      │   │ Title +      │
│ Abstract +   │   │ Abstract +   │   │ Abstract +   │
│ Metadata     │   │ Metadata     │   │ Metadata     │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────────────────┐
        │  9 EVIDENCE CATEGORIES (by strength)                 │
        │                                                       │
        │  1. Systematic Review and Meta-Analysis             │
        │     (Score: 5, Rank: 1)                             │
        │     • Cochrane reviews, PRISMA methodology          │
        │                                                       │
        │  2. RCTs and Quasi-Experimental Studies             │
        │     (Score: 4, Rank: 2)                             │
        │     • Randomized controlled trials                  │
        │     • Quasi-experimental (DiD, IV, PSM, etc.)      │
        │                                                       │
        │  3. Observational Research Studies                  │
        │     (Score: 3, Rank: 3)                             │
        │     • Cohort, case-control, cross-sectional         │
        │                                                       │
        │  4. Modelling & Simulation                           │
        │     (Score: 2, Rank: 4)                             │
        │     • Economic models, forecasts, projections        │
        │                                                       │
        │  5. Policy Syntheses & Guidance Documents            │
        │     (Score: 2, Rank: 5)                             │
        │     • White papers, policy briefs, guidance         │
        │                                                       │
        │  6. Qualitative & Contextual Evidence                │
        │     (Score: 2, Rank: 6)                             │
        │     • Interviews, focus groups, case studies        │
        │                                                       │
        │  7. Expert Opinion and Commentary                    │
        │     (Score: 1, Rank: 7)                             │
        │     • Editorials, perspectives, viewpoints           │
        │                                                       │
        │  8. Other (Non-evidence documents)                  │
        │     (Score: 0, Rank: 8)                             │
        │     • Statistical releases, bills, press releases   │
        │     • FILTERED OUT from acquisition                 │
        │                                                       │
        │  9. Unknown / Insufficient information              │
        │     (Score: 0, Rank: 9)                             │
        │     • Not enough info to classify                   │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  LLM OUTPUT FIELDS                                   │
        │  • evidence_category: str (one of 9 categories)    │
        │  • evidence_confidence: float (0.0-1.0)            │
        │  • evidence_category_reasoning: str (1-2 sentences)│
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  MERGE RESULTS INTO REFERENCES.CSV                  │
        │  • Add columns: evidence_category,                  │
        │    evidence_confidence, evidence_category_reasoning │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  FINAL FILTERING FOR ACQUISITION                    │
        │  • Keep: is_relevant = true                         │
        │  • Keep: evidence_category != "Other (Non-evidence)"│
        │  • Keep: evidence_category = "Unknown" (may reveal)  │
        └──────────────────┬──────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────┐
        │  UPDATED REFERENCES.CSV                             │
        │  Ready for acquisition pipeline                     │
        │  • All original columns                             │
        │  • + is_relevant, relevance_confidence,            │
        │    relevance_reason, top_line                       │
        │  • + evidence_category, evidence_confidence,        │
        │    evidence_category_reasoning                     │
        └─────────────────────────────────────────────────────┘
```

## Key Components

### 1. Relevance Service (`relevance.py`)

**Purpose**: Filter documents based on relevance to the research question and search context.

**Input**:
- `references.csv` with title and abstract
- Search context (research question, population, outcomes, screening factors, geography)

**Process**:
- Uses `SCREENING_MODEL` (default: `gpt-4.1-mini`)
- Batch processing: 25 documents per batch
- Evaluates each document against 5 criteria:
  1. Research question match
  2. Population interests (if specified)
  3. Outcome interests (if specified)
  4. Screening factors (if specified)
  5. Geography alignment (if specified)

**Output Fields**:
- `is_relevant`: Boolean flag
- `relevance_confidence`: Float (0.0-1.0)
  - Calculated as sum of factors: research question (+0.2), population (+0.2), outcome (+0.2), screening (+0.2), geography (+0.2)
- `relevance_reason`: Brief explanation (1-2 sentences)
- `top_line`: Executive summary (max 15 words)

**Configuration**:
- Model: `SCREENING_MODEL` = `gpt-4.1-mini`
- Batch size: 25
- Sleep time: 0.5 seconds between batches

### 2. Evidence Category Service (`evidence/category.py`)

**Purpose**: Classify relevant documents into 9 evidence categories based on methodological strength.

**Input**:
- Only documents where `is_relevant = true`
- Title, abstract, and metadata (source, type, year)

**Process**:
- Uses `EVIDENCE_CATEGORY_MODEL` (default: `gpt-5.2`)
- Batch processing: 25 documents per batch
- Classifies into one of 9 hierarchical categories

**Output Fields**:
- `evidence_category`: One of 9 category names
- `evidence_confidence`: Float (0.0-1.0)
- `evidence_category_reasoning`: Brief explanation (1-2 sentences)

**Configuration**:
- Model: `EVIDENCE_CATEGORY_MODEL` = `gpt-5.2`
- Batch size: 25
- Sleep time: 0.5 seconds between batches
- Confidence threshold: 0.5 (for workflow routing)

### 3. Evidence Categories

The 9 categories are ordered by evidence strength (highest to lowest):

1. **Systematic Review and Meta-Analysis** (Score: 5)
   - Synthesizes multiple studies
   - Keywords: "systematic review", "meta-analysis", "Cochrane", "PRISMA"

2. **RCTs and Quasi-Experimental Studies** (Score: 4)
   - Causal designs with controls
   - Keywords: "randomized controlled trial", "RCT", "quasi-experimental", "DiD", "IV", "PSM"

3. **Observational Research Studies** (Score: 3)
   - Non-randomized evidence
   - Keywords: "cohort", "case-control", "cross-sectional", "observational"

4. **Modelling & Simulation** (Score: 2)
   - Modelled/simulated evidence
   - Keywords: "simulation", "model", "forecast", "projection"

5. **Policy Syntheses & Guidance Documents** (Score: 2)
   - Policy-focused synthesis
   - Keywords: "policy brief", "white paper", "guidance", "recommendations"

6. **Qualitative & Contextual Evidence** (Score: 2)
   - Interview/qualitative evidence
   - Keywords: "qualitative", "interview", "focus group", "case study"

7. **Expert Opinion and Commentary** (Score: 1)
   - Expert commentary without empirical testing
   - Keywords: "commentary", "editorial", "perspective", "opinion"

8. **Other (Non-evidence documents)** (Score: 0)
   - Not research evidence
   - **FILTERED OUT** from acquisition
   - Keywords: "bill", "statistical bulletin", "press release"

9. **Unknown / Insufficient information** (Score: 0)
   - Not enough information to classify
   - Kept for acquisition (full text may reveal more)

### 4. Final Filtering for Acquisition

After both steps, documents are filtered for acquisition:

**Included**:
- `is_relevant = true`
- `evidence_category != "Other (Non-evidence documents)"`
- `evidence_category = "Unknown"` (kept because full text may reveal category)

**Excluded**:
- `is_relevant = false` (skipped entirely)
- `evidence_category = "Other (Non-evidence documents)"` (filtered out)

## Pipeline Integration

The filtering steps are integrated into the main analysis pipeline:

```
Step 1: References ingestion
  ↓
Step 1.5: Relevance checking (if enabled)
  ↓
Step 1.75: Evidence categorization (only for relevant docs)
  ↓
Step 2: Acquisition (only for relevant + evidence docs)
  ↓
Step 3: Parsing and normalization
  ↓
Step 4: Extraction
```

## Configuration

### Relevance Service
- **Model**: `SCREENING_MODEL` = `gpt-4.1-mini`
- **Batch size**: 25
- **Enabled**: `config.relevance_enabled` (default: `True`)

### Evidence Category Service
- **Model**: `EVIDENCE_CATEGORY_MODEL` = `gpt-5.2`
- **Batch size**: 25
- **Confidence threshold**: 0.5 (for workflow routing decisions)

## Output CSV Structure

After both steps, `references.csv` contains:

**Original columns**:
- `doc_id`, `title`, `abstract_or_summary`, `source`, `year`, etc.

**Relevance columns** (added in Step 1.5):
- `is_relevant`: bool
- `relevance_confidence`: float
- `relevance_reason`: str
- `top_line`: str

**Evidence columns** (added in Step 1.75):
- `evidence_category`: str
- `evidence_confidence`: float
- `evidence_category_reasoning`: str

**Tracking columns** (added after relevance):
- `acquisition_status`: str
- `acquisition_error`: str
- `full_text_available`: bool
- `file_path`: str
- `extraction_status`: str
- `extraction_error`: str
- `text_source`: str

## Notes

- **Relevance filtering is optional**: Can be disabled with `config.relevance_enabled = false`
- **Evidence categorization only runs on relevant documents**: More efficient use of LLM calls
- **"Unknown" category is kept**: Full text acquisition may reveal the true category
- **"Other" category is filtered out**: These documents are not evidence and won't be acquired
- **Batch processing**: Both services use batch processing for efficiency (25 docs per batch)
- **Confidence scores**: Used for downstream workflow routing (e.g., SR workflow vs RCT workflow)

