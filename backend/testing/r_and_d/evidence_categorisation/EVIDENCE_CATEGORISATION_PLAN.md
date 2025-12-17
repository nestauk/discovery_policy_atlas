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
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: ACQUISITION (existing)                                  │
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

Port the R&D `EvidenceCategoriser` class with:
- Use gpt-5.2 model (configurable via settings)
- Use variant_a prompt (baseline)
- Structured output via Pydantic
- Async batch processing with semaphore
- Note: gpt-5.2 is a thinking model so temperature is not configurable

```python
# Key components to port from R&D:
# - EvidenceClassification Pydantic model
# - CLASSIFICATION_SYSTEM_PROMPT
# - CLASSIFICATION_USER_PROMPT
# - Async classify_document() and classify_dataframe() methods
```

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

### Phase 2: Pipeline Integration

#### 2.1 Update Analysis Service
**Modify:** `backend/app/services/analysis/service.py`

Add Step 1.75 between relevance and acquisition:

```python
# After relevance check, before acquisition
if config.evidence_categorisation_enabled:
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

#### 2.2 Update RunConfig Schema
**Modify:** `backend/app/services/analysis/schemas.py`

Add configuration option:
```python
evidence_categorisation_enabled: bool = True  # Enable 9-category evidence typing
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
evidence_category: Optional[str] = None  # NEW: 9-category hierarchy
evidence_confidence: Optional[float] = None
evidence_category_reasoning: Optional[str] = None
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
evidence_category?: string
evidence_confidence?: number
evidence_category_reasoning?: string
```

#### 4.2 Update Analytics Interface
**Modify:** `frontend/components/charts/AnalyticsCharts.tsx`

Replace `document_types` with `evidence_categories` in interface.
Consider adding a new chart showing evidence category distribution.

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
- `backend/app/services/analysis/schemas.py` - Update UnifiedReference, add config
- `backend/app/services/analysis/storage.py` - Update field mappings
- `backend/app/core/config.py` - Add EVIDENCE_CATEGORY_MODEL setting
- `backend/test/test_analysis_service.py` - Update test output

### Modified Files (Frontend)
- `frontend/lib/analysisProjectStore.ts` - Update TypeScript types
- `frontend/components/charts/AnalyticsCharts.tsx` - Update analytics interface

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
2. **Backend:** Deploy code changes
3. **Frontend:** Deploy type updates
4. **Verify:** Test with new analysis runs
