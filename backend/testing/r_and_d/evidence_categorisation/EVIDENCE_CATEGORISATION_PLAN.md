# Evidence Categorisation Integration Plan

## Overview

Replace the 4-category `document_type` classification with the rigorously tested 9-category `evidence_category` hierarchy. The new categorisation runs only on relevant documents (after relevance filtering) using gpt-5.2.

## Current vs New System

### Current: 4-Category Document Type
```
- research_paper: Empirical studies, experiments, clinical trials
- reviews: Reviews, meta-analyses, systematic reviews
- policy_document: Policy recommendations, guidelines, frameworks
- other: News, announcements, opinion pieces
```

### New: 9-Category Evidence Hierarchy (ordered by evidence strength)
```
1. Systematic Review and Meta-Analysis
2. RCTs and Quasi-Experimental Studies
3. Observational Research Studies
4. Modelling & Simulation
5. Policy Syntheses & Guidance Documents
6. Qualitative & Contextual Evidence
7. Expert Opinion and Commentary
8. Other (Non-evidence documents)
9. Unknown / Insufficient information
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: REFERENCES                                              │
│ (OpenAlex, Overton ingestion)                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1.5: RELEVANCE CHECK                                       │
│ • is_relevant: bool                                             │
│ • relevance_confidence: float                                   │
│ • relevance_reason: str                                         │
│ • top_line: str                                                 │
│ • REMOVED: document_type, document_type_reason                  │
│                                                                 │
│ Model: Default LLM (cost-effective for binary relevance)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (filter: is_relevant=True)
┌─────────────────────────────────────────────────────────────────┐
│ Step 1.75: EVIDENCE CATEGORISATION (NEW)                        │
│ • evidence_category: str (9 categories)                         │
│ • evidence_confidence: float                                    │
│ • evidence_category_reasoning: str                              │
│                                                                 │
│ Model: gpt-5.2 (required for accuracy, per R&D findings)        │
│ Prompt: variant_a (baseline prompt)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (filter: exclude "Other (Non-evidence documents)")
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: ACQUISITION (existing)                                  │
│ Filters applied before processing:                              │
│ • is_relevant = True                                            │
│ • evidence_category != "Other (Non-evidence documents)"         │
│ Note: "Unknown / Insufficient information" stays - full text    │
│       may reveal more info                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: PARSING (existing)                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: EXTRACTION (existing)                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Phase 1: Backend Service Layer

#### 1.1 Create Evidence Categorisation Service
**New file:** `backend/app/services/analysis/evidence_category.py`

Follow the `RelevanceService` pattern in `relevance.py`, which uses `LLMProcessor` from `app.utils.llm.batch_check`.

**Key components:**
- Use gpt-5.2 model (configurable via settings)
- Use variant_a prompt (baseline, tested in R&D)
- Note: gpt-5.2 is a thinking model so temperature is not configurable

**Structure (mirroring RelevanceService):**
```python
class EvidenceCategoryService:
    def __init__(self, export_dir, project_id, user_id, model="gpt-5.2"):
        self.export_dir = Path(export_dir)
        self.project_id = project_id
        self.user_id = user_id
        self.model = model
        self.system_message = EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT

        # Output fields for LLM processing
        self.fields = [
            {"name": "evidence_category", "type": "str", "description": "..."},
            {"name": "evidence_confidence", "type": "float", "description": "..."},
            {"name": "evidence_category_reasoning", "type": "str", "description": "..."},
        ]

    async def categorise_documents(self, references_csv_path: str, only_relevant: bool = True) -> str:
        """Categorise documents, optionally filtering to relevant only."""
        # Load CSV, filter if only_relevant=True
        # Prepare documents dict
        # Call _screen_batch() -> _run_batch_processor()
        # Merge results back to CSV
        # Return updated CSV path

    def _run_batch_processor(self, documents, output_path):
        """Run LLMProcessor synchronously (same pattern as RelevanceService)."""
        processor = batch_check.LLMProcessor(
            model_name=self.model,
            output_path=output_path,
            system_message=self.system_message,
            output_fields=self.fields,
            # ... other params
        )
        processor.run(documents, batch_size=25, sleep_time=0.5)
```

**Port from R&D (`testing/r_and_d/evidence_categorisation/`):**
- `CLASSIFICATION_SYSTEM_PROMPT` from `prompts.py` (battle-tested)
- `EVIDENCE_CATEGORIES_DEFINITION` from `prompts.py`
- Document formatting logic from `categorise_evidence.py`

**Note:** R&D uses field name `category_reasoning` - rename to `evidence_category_reasoning` for consistency.

#### 1.2 Add Evidence Category Prompts
**Modify:** `backend/app/services/analysis/prompts.py`

Add the evidence categorisation prompts:
- EVIDENCE_CATEGORIES_DEFINITION
- EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT
- EVIDENCE_CLASSIFICATION_USER_PROMPT

#### 1.3 Update Relevance Service
**Modify:** `backend/app/services/analysis/relevance.py`

Remove document_type fields from:
- `self.fields` list (lines 71-80)
- `_merge_relevance_results()` method
- `_screen_batch()` expected columns
- RELEVANCE_SYSTEM_PROMPT in prompts.py

Keep:
- is_relevant
- relevance_confidence
- relevance_reason
- top_line

#### 1.4 Update Prompts
**Modify:** `backend/app/services/analysis/prompts.py`

Simplify RELEVANCE_SYSTEM_PROMPT to remove section 2 (document type classification).

#### 1.5 Update Synthesis Service
**Modify:** `backend/app/services/synthesis/utils.py`

The `normalize_source_type()` function (line 59) currently uses `document_type` to classify source types (NGO, IGO, etc.) for the evidence base summary. Update to use `evidence_category` instead:

```python
def normalize_source_type(source: str, evidence_category: str) -> str:
    """Normalise document source to readable category."""
    # Update logic to use evidence_category instead of document_type
    ...
```

Note: Synthesis will need to be adjusted to use the new 9-category hierarchy appropriately.

### Phase 2: Pipeline Integration

#### 2.1 Update Analysis Service
**Modify:** `backend/app/services/analysis/service.py`

Add Step 1.75 between relevance and acquisition:

```python
# After relevance check, before acquisition
with StageTimer(monitor, "evidence_categorisation"):
    evidence_service = EvidenceCategoryService(
        export_dir=str(run_export_dir),
        model=settings.EVIDENCE_CATEGORY_MODEL,  # Default: gpt-5.2
        project_id=project_id,
        user_id=user_id,
    )
    references_csv = await evidence_service.categorise_documents(
        str(references_csv),
        only_relevant=True  # Only process is_relevant=True docs
    )
```

#### 2.2 Update Acquisition Service Filtering
**Modify:** `backend/app/services/analysis/acquire.py`

Update `acquire_all()` to also filter out "Other (Non-evidence documents)" before acquisition.
Follow the existing pattern for `is_relevant` filtering (lines 50-61):

```python
# In acquire_all(), after loading CSV:
df = pd.read_csv(references_csv)

# Filter to only relevant documents if relevance checking was performed
if "is_relevant" in df.columns:
    relevant_df = df[df["is_relevant"]].copy()
    ...

# NEW: Also filter out non-evidence documents
# "Unknown / Insufficient information" stays - full text may reveal more
if "evidence_category" in relevant_df.columns:
    pre_evidence_count = len(relevant_df)
    relevant_df = relevant_df[
        relevant_df["evidence_category"] != "Other (Non-evidence documents)"
    ]
    filtered_count = pre_evidence_count - len(relevant_df)
    logger.info(
        f"Evidence filtering: excluded {filtered_count} non-evidence documents"
    )

records = relevant_df.to_dict("records")
```

#### 2.3 Add Settings Configuration
**Modify:** `backend/app/core/config.py`

Add configurable model setting:
```python
EVIDENCE_CATEGORY_MODEL: str = "gpt-5.2"  # Model for evidence categorisation
```

### Phase 3: Data Schema Updates

#### 3.1 Update UnifiedReference
**Modify:** `backend/app/services/analysis/schemas.py`

Remove:
```python
document_type: Optional[str] = None  # REMOVE
document_type_reason: Optional[str] = None  # REMOVE
```

Add:
```python
evidence_category: Optional[str] = None       # NEW: 9-category hierarchy
evidence_confidence: Optional[float] = None   # Confidence score 0.0-1.0
evidence_category_reasoning: Optional[str] = None  # Brief explanation for classification
```

#### 3.2 Update Storage Service
**Modify:** `backend/app/services/analysis/storage.py`

Update field mappings in:
- `_prepare_document_data()`
- Any CSV-to-DB mapping functions

Replace `document_type` references with `evidence_category`.

#### 3.3 Database Migration
**Note:** This migration will be done directly in Supabase.

Required changes:
```sql
-- Add new columns
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS evidence_category TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS evidence_confidence REAL DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS evidence_category_reasoning TEXT DEFAULT NULL;

-- Add index for filtering by evidence type
CREATE INDEX IF NOT EXISTS idx_analysis_documents_evidence_category
ON analysis_documents(evidence_category);

-- Keep document_type and document_type_reason columns for backward compatibility
-- Old projects will retain their existing document_type values
```

### Phase 4: Frontend Updates

#### 4.1 Update TypeScript Types
**Modify:** `frontend/lib/analysisProjectStore.ts`

Remove:
```typescript
document_type?: string  // REMOVE
document_type_reason?: string  // REMOVE
```

Add:
```typescript
evidence_category?: string           // 9-category hierarchy
evidence_confidence?: number         // Confidence score 0.0-1.0
evidence_category_reasoning?: string // Brief explanation for classification
```

#### 4.2 Update Analytics Interface
**Modify:** `frontend/components/charts/AnalyticsCharts.tsx`

Replace `document_types` with `evidence_categories` in interface.
Consider adding a new chart showing evidence category distribution.

#### 4.3 Post-Integration Frontend Updates (deferred)
After initial backend integration is complete, additional frontend updates needed:
- **Evidence Table** - Update to display `evidence_category` instead of `document_type`
- **Executive Summary** - Update evidence base summary to use new categories

### Phase 5: Testing

#### 5.1 Update Tests
**Modify:** `backend/test/test_analysis_service.py`

Update debug output to show `evidence_category` instead of `document_type`.

## Files Changed Summary

### New Files
- `backend/app/services/analysis/evidence_category.py` - Main service

### Modified Files (Backend)
- `backend/app/services/analysis/prompts.py` - Add evidence prompts, simplify relevance
- `backend/app/services/analysis/relevance.py` - Remove document_type
- `backend/app/services/analysis/service.py` - Add Step 1.75
- `backend/app/services/analysis/acquire.py` - Filter out "Other (Non-evidence documents)"
- `backend/app/services/analysis/schemas.py` - Update UnifiedReference
- `backend/app/services/analysis/storage.py` - Update field mappings
- `backend/app/services/synthesis/utils.py` - Update normalize_source_type() to use evidence_category
- `backend/app/core/config.py` - Add EVIDENCE_CATEGORY_MODEL setting
- `backend/test/test_analysis_service.py` - Update test output

### Modified Files (Frontend)
- `frontend/lib/analysisProjectStore.ts` - Update TypeScript types
- `frontend/components/charts/AnalyticsCharts.tsx` - Update analytics interface

## R&D Findings

The evidence categorisation system was rigorously tested in `testing/r_and_d/evidence_categorisation/`.

### Experiment Setup
- **Datasets:** 3 validation sets (child_obesity, home_heating, intervention_home_learning) with human-labelled ground truth
- **Models tested:** gpt-5-mini, gpt-5, gpt-5.2
- **Prompt variants:** variant_a (baseline), variant_b (strengthened Unknown definition)

### Key Results
- **gpt-5.2** achieved highest accuracy (~70-73%) across datasets
- **gpt-5-mini** showed lower accuracy (~43-60%)
- **variant_a and variant_b** performed similarly with gpt-5.2
- Confidence scores correlate with correctness (correct predictions have higher confidence)

### R&D Files Reference
- `categorise_evidence.py` - Main classification script using `LLMProcessor`
- `prompts.py` - Battle-tested prompts (`CLASSIFICATION_SYSTEM_PROMPT`, `EVIDENCE_CATEGORIES_DEFINITION`)
- `validate_classifier.py` - Validation metrics calculation
- `experiments/` - Full experiment framework (run_experiment.py, collect_results.py, visualize_results.py)

### Field Name Note
R&D uses `category_reasoning` - production will use `evidence_category_reasoning` for consistency with other fields.

## Configuration

### Model for Evidence Categorisation
Based on R&D findings:
- **Model:** `gpt-5.2` (configurable via `EVIDENCE_CATEGORY_MODEL` setting)
- **Prompt:** variant_a (baseline prompt - same accuracy as variant_b with gpt-5.2)

Note: gpt-5.2 is a thinking model, so temperature parameter is not applicable.

### Cost Considerations
- Evidence categorisation runs only on relevant documents
- gpt-5.2 is more expensive but necessary for accuracy
- Relevance filtering continues to use default/cheaper model

## Backward Compatibility

### Database
- Keep `document_type` and `document_type_reason` columns in database
- Old projects retain their existing `document_type` values
- New runs populate `evidence_category` fields only
- No migration of existing data

### Frontend
- Frontend gracefully handles missing `evidence_category` (shows N/A or similar)
- Old projects will not have evidence_category data

## Rollout Strategy

1. **Database:** Add new columns in Supabase (evidence_category, evidence_confidence, evidence_category_reasoning)
2. **Backend:**
   - Create `EvidenceCategoryService` following `RelevanceService` pattern
   - Port prompts from R&D to `prompts.py`
   - Update `RelevanceService` to remove document_type fields
   - Integrate into pipeline (`service.py`)
3. **Frontend:** Deploy type updates
4. **Verify:** Test with new analysis runs
5. **Cleanup:** R&D code can remain for future experiments/validation
