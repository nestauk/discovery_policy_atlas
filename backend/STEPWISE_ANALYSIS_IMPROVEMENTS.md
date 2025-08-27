# Stepwise Analysis Data Storage Improvements

## Overview

Enhanced the analysis service to store data incrementally during the analysis pipeline and capture significantly more document metadata. This provides immediate feedback to users and preserves rich data that was previously lost.

## Key Improvements

### 1. Enhanced Database Schema

**File**: `backend/supabase_schema_enhancement.sql`

Added comprehensive fields to `analysis_documents` table:

#### New Core Fields
- `authors` (JSONB) - Array of author names
- `doi` (TEXT) - Document DOI identifier  
- `source_id` (TEXT) - Original source identifier
- `landing_page_url` (TEXT) - Link to document page
- `pdf_url` (TEXT) - Direct PDF link
- `venue` (TEXT) - Publication venue
- `citation_count` (INTEGER) - Citation metrics

#### Relevance & Quality Fields
- `relevance_confidence` (REAL) - AI confidence score
- `relevance_reason` (TEXT) - Explanation of relevance
- `top_line` (TEXT) - Key takeaway summary
- `document_type` (TEXT) - Document classification
- `document_type_reason` (TEXT) - Classification rationale

#### Geographic & Source Fields  
- `source_country` (TEXT) - Country of origin
- `source_type` (TEXT) - Type of publication
- `author_institution_countries` (JSONB) - Countries of author institutions
- `topics` (JSONB) - Topic classifications
- `published_on` (TEXT) - Publication date
- `overton_url` (TEXT) - Overton database link

#### Acquisition & Processing Tracking
- `acquisition_status` (TEXT) - Download success/failure
- `acquisition_error` (TEXT) - Error details if failed
- `full_text_available` (BOOLEAN) - Whether full text was obtained
- `file_path` (TEXT) - Local file location
- `extraction_error` (TEXT) - Extraction error details
- `text_source` (TEXT) - Whether extracted from full text or abstract

#### Upload Step Tracking
- `upload_step` (TEXT) - Tracks data progression: `initial`, `screened`, `acquired`, `extracted`, `completed`

### 2. Stepwise Upload System

**File**: `backend/app/services/analysis/storage.py`

#### New Methods

**`store_initial_documents(project_id, references)`**
- Called after screening/relevance checking phase
- Stores documents with all available metadata immediately
- Users can see evidence tab populated early in analysis

**`update_documents_with_extractions(project_id, extractions_json_path)`**
- Called after extraction phase completes
- Updates existing documents with extraction results
- Preserves all previously stored metadata

**`_map_reference_to_document(ref, project_id, upload_step)`**
- Comprehensive mapping from `UnifiedReference` schema to database fields
- Handles all new fields with proper type conversion
- Tracks upload progression via `upload_step`

**`_upsert_documents(documents_data)`**
- Uses Supabase upsert for handling document updates
- Prevents duplicates while allowing progressive data enhancement

### 3. Analysis Service Integration

**File**: `backend/app/services/analysis/service.py`

#### Stepwise Upload Points

1. **After Relevance Checking (Lines 113-123)**
   ```python
   # STEPWISE UPLOAD: Store initial documents after screening
   if project_id:
       await self._store_initial_documents(project_id, references_csv)
   ```

2. **CSV-to-Schema Conversion**
   - `_load_references_from_csv()` - Converts CSV data to `UnifiedReference` objects
   - Comprehensive field mapping with type safety
   - Robust parsing for lists, JSON fields, and nullable values

#### Data Conversion Utilities
- `_safe_str()`, `_safe_int()`, `_safe_float()`, `_safe_bool()` - Type-safe conversions
- `_parse_authors()` - Handles author lists in various formats (JSON, comma-separated)
- `_parse_list()` - Generic list field parsing with JSON fallback

## User Experience Improvements

### Immediate Feedback
- Evidence tab populates immediately after screening (~30 seconds)
- Shows document titles, sources, relevance scores, and abstracts
- No need to wait for full analysis completion

### Rich Metadata Display
- Author information preserved and displayed
- DOI links and venue information available
- Geographic data (source countries) for filtering
- Relevance explanations and confidence scores
- Document type classifications

### Progressive Enhancement
- Initial upload provides basic document info
- Subsequent phases add acquisition status
- Final phase adds extraction results
- Each step enhances the same records rather than replacing

## Implementation Details

### Database Performance
- Added strategic indexes on commonly queried fields
- Unique constraint handles upserts without conflicts
- JSONB fields for complex data with query support

### Error Handling
- Stepwise uploads are non-blocking (failures don't stop analysis)
- Comprehensive logging for debugging
- Graceful degradation when optional fields are missing

### Field Compatibility
- Maps to existing frontend `Paper` interface
- Backward compatible with old document structures
- Additional fields available for future enhancements

## Usage

### Running the Schema Migration
```sql
-- Run in Supabase SQL editor
\i backend/supabase_schema_enhancement.sql
```

### Automatic Integration
The stepwise uploads are automatically integrated into the analysis pipeline:

1. User starts analysis from frontend
2. After screening: Documents appear in Evidence tab with basic info
3. After acquisition: Status updates show download progress  
4. After extraction: Full analysis results available
5. Throughout: Real-time progress visible to users

### Benefits

1. **Immediate User Feedback** - Evidence visible within ~30 seconds
2. **Rich Data Preservation** - No loss of valuable metadata
3. **Better UX** - Progressive loading vs. all-or-nothing
4. **Debugging Support** - Track where analysis stages fail
5. **Future Compatibility** - Schema supports advanced features

This enhancement transforms the analysis from a black-box process to a transparent, progressive workflow with rich data preservation.