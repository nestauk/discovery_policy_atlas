# Evidence Categorisation Design

## Goal
Classify documents from references.csv into 7 hierarchical evidence categories using LLM-based classification.

## Input
- **Source**: `references.csv` files (from OpenAlex/Overton searches)
- **Key fields**: `title`, `abstract_or_summary`, `type`, `source`, `document_type`

## Output
- Enhanced CSV with:
  - `evidence_category`: One of 7 categories
  - `evidence_confidence`: 0.0-1.0 score
  - `category_reasoning`: Brief explanation

## Classification Approach

### Single-pass LLM Classification
Use gpt-5-mini with structured output for cost-effective batch classification:

```
For each document:
  Input: title + abstract + metadata
  Output: {category, confidence, reasoning}
```

### Prompt Strategy
Provide LLM with:
1. The 7 category definitions (from your specification)
2. Document metadata (title, abstract, type, source)
3. Ask for single best-fit category + confidence

### Category Hierarchy (highest to lowest evidence strength)
1. Systematic review and meta-analysis
2. RCTs and quasi-experimental studies
3. Observational Research Studies
4. Modelling & Simulation
5. Policy Syntheses & Guidance Documents
6. Qualitative & Contextual evidence
7. Expert opinion and commentary

## Implementation Plan

### 1. Core Script: `categorise_evidence.py`
```python
# Read references.csv
# For each document:
#   - Extract title, abstract, metadata
#   - Call LLM with classification prompt
#   - Parse structured response
#   - Add to output DataFrame
# Write enhanced CSV
```

### 2. Prompt Engineering
Create a single system prompt with:
- Clear definitions of all 7 categories
- Examples of each category (2-3 per category)
- Instructions for edge cases
- Request structured JSON output

### 3. Batch Processing
- Process documents in batches (e.g., 10 at a time)
- Add progress tracking
- Handle API errors gracefully
- Cache results to resume on failure

## Signal Keywords (Optional Enhancement)
If LLM classification is ambiguous, use keyword signals:

| Category | Keywords |
|----------|----------|
| Systematic Review | "systematic review", "meta-analysis", "Cochrane", "PRISMA" |
| RCT | "randomized controlled trial", "RCT", "randomisation", "treatment arm" |
| Observational | "cohort", "case-control", "cross-sectional", "observational" |
| Modelling | "simulation", "model", "forecast", "projection" |
| Policy Synthesis | "policy brief", "white paper", "guidance", "recommendations" |
| Qualitative | "qualitative", "interview", "focus group", "case study", "thematic" |
| Expert Opinion | "commentary", "editorial", "perspective", "opinion", "viewpoint" |

## Validation Strategy
1. **Confidence analysis**: Review low-confidence (<0.6) classifications
2. **Category distribution**: Check if distribution makes sense
3. **Manual review**: Sample-check classifications across categories (future step)

## File Structure
```
evidence_categorisation/
├── DESIGN.md                 # This file
├── README.md                # Usage instructions
├── categorise_evidence.py    # Main script
├── prompts.py               # Classification prompts
├── inputs/                  # Input references.csv files
│   └── references.csv
└── outputs/                 # Categorized results
    └── categorised_evidence.csv
```
