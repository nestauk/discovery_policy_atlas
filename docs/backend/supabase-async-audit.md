# Supabase Queries - Async Conversion Audit

**Date**: October 7, 2025  
**Status**: ✅ COMPLETED

---

## Overview

All Supabase queries in the codebase are currently **synchronous** (blocking the event loop), except for a few in `storage.py` that use `run_in_executor()`.

### Impact
- Each synchronous query blocks the event loop for 50-500ms
- Multiple queries in sequence = significant blocking time
- Backend becomes unresponsive during data operations

---

## Analysis Service - Supabase Queries

### File: `storage.py` (18 queries total)

#### ✅ Already Async (using executor):
1. **Line 584-590**: `store_extractions_from_json()` - Document ID mapping
   ```python
   doc_response = await loop.run_in_executor(
       None,
       lambda: self.supabase.table("analysis_documents")...
   )
   ```

2. **Line 818-820**: `_upload_references_to_db()` - Batch document inserts
3. **Line 833-835**: Check existing documents
4. **Line 851-853**: Update documents
5. **Line 860-862**: Insert new documents

#### ❌ Still Synchronous (need to convert):

**High Priority** (in hot paths, called frequently):

6. **Line 110-113**: `check_existing_extractions()` 
   ```python
   self.supabase.table("analysis_documents")
       .select("doc_id,extraction_status")
       .eq("analysis_project_id", project_id)
       .execute()
   ```
   - **Impact**: Called during extraction for every project
   - **Fix**: Wrap in `run_in_executor()`

7. **Line 156-159**: `store_single_extraction()` - Update document status
   - **Impact**: Called for each document during extraction
   - **Fix**: Wrap in `run_in_executor()`

8. **Line 187-189**: Delete extractions (before insert)
   - **Impact**: Called for each document
   - **Fix**: Wrap in `run_in_executor()`

9. **Line 192-194**: Insert extraction items
   - **Impact**: Called for each document
   - **Fix**: Wrap in `run_in_executor()`

10. **Line 233-236**: `store_document_chunks()` - Get document ID
    - **Impact**: Called for each document
    - **Fix**: Wrap in `run_in_executor()`

11. **Line 266-268**: Delete existing chunks
    - **Impact**: Called for each document
    - **Fix**: Wrap in `run_in_executor()`

12. **Line 278-280**: Insert chunks (batched)
    - **Impact**: Called multiple times per document
    - **Fix**: Wrap in `run_in_executor()`

**Medium Priority** (less frequent, but still important):

13. **Line 429-430**: `store_analysis_run()` - Create project
    - **Impact**: Once per analysis run
    - **Fix**: Wrap in `run_in_executor()`

14. **Line 451-454**: Update project metadata
    - **Impact**: Once per analysis run
    - **Fix**: Wrap in `run_in_executor()`

15. **Line 618-620**: Batch insert extractions (in loop)
    - **Impact**: Once per 100 extractions
    - **Fix**: Wrap in `run_in_executor()`

16. **Line 632-636**: Update project with extractions count
    - **Impact**: Once per run
    - **Fix**: Wrap in `run_in_executor()`

17. **Line 651-655**: Update project on error
    - **Impact**: On error only
    - **Fix**: Wrap in `run_in_executor()`

18. **Line 879-882**: Batch update documents
    - **Impact**: Once per run
    - **Fix**: Wrap in `run_in_executor()`

---

## Synthesis Service - Supabase Queries

### File: `service.py` (9 queries total)

#### ❌ All Synchronous (need to convert):

**High Priority** (in hot paths):

1. **Line 47-50**: `summarise()` - Get project info
   ```python
   self.supabase.table("analysis_projects")
       .select("*")
       .eq("id", project_id)
       .execute()
   ```
   - **Impact**: Start of synthesis, blocks for ~100ms
   - **Fix**: Wrap in `run_in_executor()`

2. **Line 60-63**: Get all documents for project
   - **Impact**: Blocks for 100-500ms depending on document count
   - **Fix**: Wrap in `run_in_executor()`

3. **Line 77-80**: Get all extractions for project
   - **Impact**: Blocks for 500-2000ms with many extractions
   - **Fix**: Wrap in `run_in_executor()`

4. **Line 493-496**: `get_findings()` - Get documents
   - **Impact**: Called when drilling down into findings
   - **Fix**: Wrap in `run_in_executor()`

**Medium Priority** (less frequent):

5. **Line 517-520**: Get synthesis runs (for theme assignments)
   - **Impact**: Optional feature, moderate frequency
   - **Fix**: Wrap in `run_in_executor()`

6. **Line 530-533**: Get issue themes
   - **Impact**: When using theme assignments
   - **Fix**: Wrap in `run_in_executor()`

7. **Line 540-543**: Get intervention themes
   - **Impact**: When using theme assignments
   - **Fix**: Wrap in `run_in_executor()`

8. **Line 552-555**: Get theme assignments
   - **Impact**: When using theme assignments
   - **Fix**: Wrap in `run_in_executor()`

9. **Line 562-565**: Get extraction details
   - **Impact**: When using theme assignments with many extractions
   - **Fix**: Wrap in `run_in_executor()`

---

## Recommended Implementation Strategy

### Option 1: Helper Function Pattern (Recommended)

Create a reusable helper in each service:

```python
async def _async_supabase_query(self, query_func):
    """Execute a Supabase query asynchronously in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query_func)
```

**Usage**:
```python
# Before (blocking)
result = self.supabase.table("analysis_projects").select("*").eq("id", project_id).execute()

# After (non-blocking)
result = await self._async_supabase_query(
    lambda: self.supabase.table("analysis_projects")
        .select("*")
        .eq("id", project_id)
        .execute()
)
```

### Option 2: Async Supabase Client (Future Enhancement)

Use an async Supabase client library (if available) for true async I/O.

**Pros**:
- True async I/O (more efficient than thread pool)
- Better connection pooling
- Modern async/await patterns

**Cons**:
- Requires library change
- More refactoring needed
- May not be available for Supabase Python SDK

### Option 3: Hybrid Approach (Current)

- Keep using `run_in_executor()` for existing patterns
- Add helper function for new code
- Gradually migrate old code

---

## Priority Order for Implementation

### Phase 1: Synthesis Service (Immediate - Highest Impact)
**Estimated Time**: 1-2 hours

The synthesis service queries are in the hot path and cause noticeable blocking:

1. ✅ **Lines 47-50, 60-63, 77-80** - Initial data loading in `summarise()`
   - These three queries run sequentially at the start
   - Total blocking: ~700-2000ms
   - **HIGH IMPACT**: Convert these first

2. **Line 493-496** - `get_findings()` document query
   - Called when drilling into specific findings
   - Blocking: ~100-500ms

### Phase 2: Analysis Storage Service (High Impact)
**Estimated Time**: 2-3 hours

Focus on hot paths first:

1. **Lines 110-113** - `check_existing_extractions()`
2. **Lines 156-194** - `store_single_extraction()` operations
3. **Lines 233-280** - `store_document_chunks()` operations

### Phase 3: Remaining Analysis Service (Medium Impact)
**Estimated Time**: 1-2 hours

Less frequent but still important:
1. Project creation/update operations
2. Batch operations
3. Error handling updates

---

## Expected Performance Improvements

### Synthesis Service

**Before** (all queries synchronous):
```
Load project:     100ms (blocking)
Load documents:   300ms (blocking)  
Load extractions: 1500ms (blocking)
Total:           ~1900ms of blocking
```

**After** (all queries async):
```
All queries:     ~1900ms (but non-blocking!)
Backend:         Remains responsive to other requests
Throughput:      Can handle multiple synthesis requests concurrently
```

### Analysis Service

**Before**:
- 100 documents × 4 queries each = 400 blocking operations
- Average 200ms per query = 80 seconds of blocking

**After**:
- Same wall-clock time, but backend responsive
- Can process multiple analysis runs concurrently

---

## Testing Checklist

After implementing async queries:

- [ ] Run synthesis test script - verify no errors
- [ ] Check logs for "Using OpenAI" and successful queries
- [ ] Monitor resource usage (should see higher concurrent tasks)
- [ ] Test with multiple concurrent requests
- [ ] Verify no race conditions in batch operations
- [ ] Check error handling still works

---

## Code Examples

### Before:
```python
async def summarise(self, project_id: str) -> SynthesisSummary:
    # BLOCKING - holds up the entire event loop
    project_res = self.supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
    
    # BLOCKING - can't process other requests during this
    docs_res = self.supabase.table("analysis_documents").select("*").eq("analysis_project_id", project_id).execute()
```

### After (Option 1 - Helper Function):
```python
async def summarise(self, project_id: str) -> SynthesisSummary:
    # NON-BLOCKING - event loop remains free
    project_res = await self._async_supabase_query(
        lambda: self.supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
    )
    
    # NON-BLOCKING - other requests can be processed
    docs_res = await self._async_supabase_query(
        lambda: self.supabase.table("analysis_documents").select("*").eq("analysis_project_id", project_id).execute()
    )
```

### After (Option 2 - Parallel Queries):
```python
async def summarise(self, project_id: str) -> SynthesisSummary:
    # PARALLEL - both queries run concurrently!
    project_res, docs_res = await asyncio.gather(
        self._async_supabase_query(
            lambda: self.supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
        ),
        self._async_supabase_query(
            lambda: self.supabase.table("analysis_documents").select("*").eq("analysis_project_id", project_id).execute()
        )
    )
```

---

## Summary

**Total Supabase Queries**: 27
- Analysis Service: 18 queries
  - Already async: 5 (28%)
  - Converted to async: 13 (72%) ✅
- Synthesis Service: 9 queries
  - Converted to async: 9 (100%) ✅

**Actual Time Taken**: ~2 hours
**Expected Benefit**: 5-10x improvement in concurrent request handling

---

## ✅ IMPLEMENTATION COMPLETED

### What Was Done

1. **Added `_async_supabase_query()` helper** to both services
   - Executes queries in thread pool using `run_in_executor()`
   - Prevents blocking the event loop
   - Includes semaphore for concurrency control

2. **Added Semaphore for Concurrency Control**
   - Both services: `asyncio.Semaphore(50)`
   - Limits to 50 concurrent DB queries per service
   - Prevents DB connection exhaustion
   - Prevents thread pool exhaustion
   - Provides automatic backpressure

3. **Converted ALL Supabase queries** (27 total)
   - Synthesis Service: 9/9 ✅
   - Analysis Storage Service: 18/18 ✅

### Files Modified

- `backend/app/services/synthesis/service.py`:
  - Added semaphore initialization
  - Converted all 9 queries to async
  
- `backend/app/services/analysis/storage.py`:
  - Added semaphore initialization
  - Converted all 13 remaining queries to async
  - (5 were already async from previous work)

### Safety Measures Implemented

✅ **Concurrency Limiting**: 50 concurrent queries max per service  
✅ **Non-blocking I/O**: All queries use thread pool  
✅ **Backpressure**: Semaphore queues requests when at capacity  
❌ **Timeouts**: Not implemented (analysis can take 20+ mins)  

### Testing Checklist

- [ ] Run synthesis test script with monitoring
- [ ] Run analysis test script with monitoring
- [ ] Check resource usage with `ResourceMonitor`
- [ ] Verify no DB connection errors under load
- [ ] Test with multiple concurrent requests
- [ ] Verify semaphore is limiting concurrency as expected

### Next Steps

1. Test with existing test scripts
2. Monitor concurrent task counts
3. Adjust semaphore limits if needed (can increase to 100 if DB supports it)
4. Consider adding metrics/logging for semaphore wait times

