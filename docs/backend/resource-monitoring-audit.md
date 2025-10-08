# Resource Monitoring & Optimization Audit

**Date**: October 7, 2025  
**Services Audited**: Analysis Service, Synthesis Service  
**Goal**: Identify bottlenecks, async/sync operations, and implement monitoring

---

## Executive Summary

Both Analysis and Synthesis services have **mixed async/sync operations** that can cause backend stalling. Key issues:

1. **Synchronous bottlenecks** in PDF parsing, file I/O, and some LLM calls
2. **No guardrails** on file sizes, processing timeouts, or memory limits
3. **Limited concurrency** in critical paths (default 3-5 parallel operations)
4. **No resource monitoring** to track CPU, RAM, or concurrent operations
5. **Database operations** are synchronous (Supabase client)

---

## 1. ANALYSIS SERVICE AUDIT

### 1.1 Service Flow (`service.py`)

**Overall**: `async` orchestrator

#### Step-by-Step Operations:

| Step | Function | Async/Sync | Concurrency | Bottleneck Risk |
|------|----------|------------|-------------|-----------------|
| 1. References | `ReferencesService.build_references()` | ✅ Async | N/A | Low |
| 1.5. Relevance | `RelevanceService.check_relevance()` | ✅ Async | Batch 25 | Medium |
| 2. Acquisition | `AcquisitionService.acquire_all()` | ✅ Async | **5 concurrent** | Medium |
| 3. Parsing | `ParsingService.parse_saved_file()` | ❌ **SYNC** | Sequential | **HIGH** |
| 4. Normalization | `normalize_text()` | ❌ **SYNC** | Sequential | Low |
| 4. File I/O | `Path.write_text()` | ❌ **SYNC** | Sequential | Medium |
| 5. Extraction | `LangChainExtractorService.extract_for_documents()` | ✅ Async | **3 concurrent** | Medium-High |
| 6. Storage | `AnalysisStorageService.store_analysis_run()` | ✅ Async | N/A | Low |

### 1.2 Acquisition Service (`acquire.py`)

**Status**: ✅ Properly async

- Uses `asyncio.gather()` with semaphore (default: 5 concurrent downloads)
- HTTP calls via `httpx.AsyncClient` (30s timeout)
- **Issue**: No file size limits before downloading PDFs
- **Issue**: No maximum retry logic

**Recommendations**:
- ✅ Already has timeout (30s)
- ❌ Add file size limit check (HEAD request before download)
- ❌ Add max file size limit (e.g., 50MB)

### 1.3 Parsing Service (`parse.py`)

**Status**: ❌ **COMPLETELY SYNCHRONOUS** - **MAJOR BOTTLENECK**

```python
def parse_saved_file(self, doc_id: str, file_path: str) -> Optional[ParsedText]:
    # This is SYNC and blocks the event loop!
    if path.suffix.lower() == ".pdf":
        return self._parse_pdf(doc_id, path)  # PyMuPDF is sync
```

**Issues**:
1. PDF parsing via PyMuPDF (`fitz.open()`) is **synchronous** and CPU-intensive
2. Large PDFs (100+ pages) can block for 10-30 seconds
3. No size/page limit checks before parsing
4. No timeout mechanism

**Impact**: For 100 documents with 50% PDFs, if average PDF takes 5s to parse = **~4 minutes of blocking**

**Recommendations**:
- ✅ Run in thread pool executor (`loop.run_in_executor()`)
- ✅ Add PDF page count limit (e.g., 200 pages max)
- ✅ Add file size limit before parsing (e.g., 50MB max)
- ✅ Add per-document parsing timeout (e.g., 30s)

### 1.4 Extraction Service (`extractor_langchain.py`)

**Status**: ✅ Async with controlled concurrency

```python
sem = asyncio.Semaphore(self.config.concurrency)  # Default: 3
results = await asyncio.gather(*[_guarded(r) for _, r in df.iterrows()])
```

**Issues**:
1. Low default concurrency (3) - could be increased
2. Text truncation (`tiktoken.encode()`) is **synchronous**
3. File reads (`Path.read_text()`) are **synchronous**
4. No per-document timeout

**Recommendations**:
- ✅ Increase default concurrency to 5-10 (configurable)
- ✅ Move tiktoken operations to thread pool
- ✅ Use async file I/O (`aiofiles`)
- ✅ Add per-document extraction timeout (e.g., 120s)

### 1.5 Workflow (`workflow_langchain.py`)

**Status**: ✅ Async LangGraph workflow

- All LLM calls use `ainvoke()` (async)
- Sequential processing through stages (by design)
- **Issue**: No timeout on individual LLM calls

**Recommendations**:
- ✅ Add timeout wrapper around LLM invocations

### 1.6 Relevance Service (`relevance.py`)

**Status**: ⚠️ Mixed - uses thread pool for sync batch processor

```python
await loop.run_in_executor(None, self._run_batch_processor, ...)
```

**Good**: Already wraps sync LLM processor in executor  
**Issue**: No individual document timeout

---

## 2. SYNTHESIS SERVICE AUDIT

### 2.1 Legacy Service (`synthesis/service.py`)

**Status**: ❌ **MOSTLY SYNCHRONOUS** - **MAJOR BOTTLENECK**

#### Critical Issues:

1. **Supabase queries are ALL synchronous**:
```python
project_res = self.supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
# This blocks the event loop!
```

2. **LLM calls are synchronous** in `call_llm_cluster()` and `call_llm_executive_briefing()`:
```python
llm = get_llm(settings.LLM_MODEL, temperature=0.0)
resp = llm.invoke(prompt.format())  # SYNC, not ainvoke()!
```

3. **Large data loading in memory**:
   - Loads all documents and extractions at once
   - No pagination or streaming

**Impact**: For 500 documents:
- Supabase queries: ~5-10s (blocking)
- LLM clustering: ~30-60s (blocking)
- Executive briefing: ~10-20s (blocking)
- **Total blocking time: 45-90 seconds**

**Recommendations**:
- ✅ Convert all LLM calls to `ainvoke()`
- ✅ Use async Supabase client or wrap in executor
- ✅ Add timeouts on LLM calls
- ⚠️ Consider pagination for large datasets

### 2.2 Agent-based Service (`synthesis/agent.py`)

**Status**: ✅ Mostly async, but with sync database calls

**Good**:
- LLM calls use `ainvoke()` (async)
- Concept mapping uses `asyncio.gather()` with high concurrency (32)
- Structured LangGraph workflow

**Issues**:
1. **Supabase queries still synchronous**:
```python
docs_res = supabase.table("analysis_documents").select("id, doc_id").eq("analysis_project_id", project_id).execute()
```

2. Large batch operations in memory
3. No timeout on individual LLM calls

**Recommendations**:
- ✅ Wrap Supabase calls in executor
- ✅ Add LLM timeout wrappers
- ✅ Consider streaming for large concept sets

---

## 3. IDENTIFIED BOTTLENECKS (Priority Order)

### 🔴 CRITICAL (Blocks event loop):

1. **PDF Parsing** (`parse.py`) - Synchronous PyMuPDF operations
2. **File I/O** - Synchronous read/write operations throughout
3. **Supabase Queries** (Synthesis) - All database operations are synchronous
4. **LLM calls** (Synthesis legacy) - Using `invoke()` instead of `ainvoke()`

### 🟡 MEDIUM (Limits throughput):

5. **Low concurrency** - Extraction limited to 3, acquisition to 5
6. **Text truncation** - Synchronous tiktoken encoding
7. **No timeouts** - Operations can hang indefinitely

### 🟢 LOW (Minor impact):

8. **Memory usage** - Loading large datasets entirely in memory
9. **No progress tracking** - Can't monitor long-running operations

---

## 4. RECOMMENDED GUARDRAILS

### 4.1 File Size Limits

```python
# PDF files
MAX_PDF_SIZE_MB = 50  # Skip files larger than 50MB
MAX_PDF_PAGES = 200   # Skip PDFs with more than 200 pages

# Text truncation
MAX_CONTEXT_TOKENS = 100_000  # Already implemented
```

### 4.2 Timeout Limits

```python
# Network operations
DOWNLOAD_TIMEOUT = 30.0  # Already implemented
SCRAPE_TIMEOUT = 30.0    # Already implemented

# Processing operations
PDF_PARSE_TIMEOUT = 30.0      # NEW: Per-document parsing
EXTRACTION_TIMEOUT = 120.0     # NEW: Per-document extraction
LLM_CALL_TIMEOUT = 60.0        # NEW: Individual LLM calls

# Pipeline timeouts
ANALYSIS_RUN_TIMEOUT = 3600    # NEW: 1 hour max for full analysis
SYNTHESIS_RUN_TIMEOUT = 600    # NEW: 10 minutes max for synthesis
```

### 4.3 Concurrency Limits

```python
# Current values
ACQUISITION_CONCURRENCY = 5    # Keep as is
EXTRACTION_CONCURRENCY = 3     # INCREASE to 5-10

# Recommended values
EXTRACTION_CONCURRENCY = 10    # Based on API rate limits
RELEVANCE_BATCH_SIZE = 25      # Keep as is
CONCEPT_MAPPING_CONCURRENCY = 32  # Keep as is (synthesis/agent.py)
```

### 4.4 Memory Limits

```python
# Consider implementing
MAX_DOCUMENTS_IN_MEMORY = 1000  # Paginate larger datasets
MAX_TEXT_LENGTH_CHARS = 500_000 # Skip extremely large documents
```

---

## 5. RECOMMENDED OPTIMIZATIONS

### 5.1 Make Parsing Async (HIGH PRIORITY)

```python
# In parse.py
async def parse_saved_file(self, doc_id: str, file_path: str) -> Optional[ParsedText]:
    path = Path(file_path)
    if not path.exists():
        return None
    
    # Run in thread pool to not block event loop
    loop = asyncio.get_event_loop()
    try:
        if path.suffix.lower() == ".pdf":
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._parse_pdf, doc_id, path),
                timeout=PDF_PARSE_TIMEOUT
            )
        else:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._parse_html, doc_id, path),
                timeout=PDF_PARSE_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning(f"Parsing timeout for {doc_id}")
        return None
```

### 5.2 Fix Synthesis LLM Calls (HIGH PRIORITY)

```python
# In synthesis/service.py - call_llm_cluster()
llm = get_llm(settings.LLM_MODEL, temperature=0.0)
resp = await llm.ainvoke(prompt.format())  # Change invoke -> ainvoke
```

### 5.3 Wrap Supabase in Executor (MEDIUM PRIORITY)

```python
# Helper function
async def async_supabase_query(query_func):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query_func)

# Usage
docs_res = await async_supabase_query(
    lambda: self.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
)
```

### 5.4 Async File I/O (MEDIUM PRIORITY)

```python
# Use aiofiles for all file operations
import aiofiles

async with aiofiles.open(out_path, 'w', encoding='utf-8') as f:
    await f.write(norm_text)
```

---

## 6. MONITORING REQUIREMENTS

### 6.1 What to Monitor

**Resource Metrics**:
- CPU usage (%)
- RAM usage (MB)
- Active async tasks count
- Thread pool utilization

**Pipeline Metrics**:
- Documents processed count
- Current processing stage
- Documents per second (throughput)
- Errors/failures count

**Timing Metrics**:
- Per-stage duration
- Per-document processing time
- Queue wait times

### 6.2 Where to Add Monitoring

1. **Analysis Service** (`service.py`):
   - Before/after each major step
   - Log resource usage and timing

2. **Extraction Service** (`extractor_langchain.py`):
   - Inside `_process_row()` for per-document metrics
   - After batch completion

3. **Synthesis Service** (`service.py`, `agent.py`):
   - Before/after each workflow node
   - Track LLM call counts and timing

### 6.3 Monitoring Implementation

Create a lightweight `ResourceMonitor` utility:

```python
class ResourceMonitor:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = None
        self.metrics = {}
    
    def snapshot(self, label: str):
        """Take a snapshot of current resource usage"""
        import psutil
        import asyncio
        
        process = psutil.Process()
        
        return {
            "label": label,
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "threads": process.num_threads(),
            "active_tasks": len(asyncio.all_tasks()),
        }
    
    def log_snapshot(self, label: str):
        snapshot = self.snapshot(label)
        logger.info(f"[{self.service_name}] {label}: "
                   f"CPU={snapshot['cpu_percent']:.1f}% "
                   f"RAM={snapshot['memory_mb']:.1f}MB "
                   f"Threads={snapshot['threads']} "
                   f"Tasks={snapshot['active_tasks']}")
```

---

## 7. TESTING REQUIREMENTS

### 7.1 Unit Tests

For each service step:
- Test with small input (1-5 documents)
- Test with timeout scenarios
- Test with oversized files
- Test with corrupted files

### 7.2 Integration Tests

End-to-end pipeline tests:
- Small dataset (10 docs)
- Medium dataset (50 docs)
- Large dataset (200 docs)
- Monitor resource usage throughout

### 7.3 Load Tests

Stress testing:
- Concurrent analysis runs
- Maximum document counts
- Network failures during acquisition
- LLM API rate limiting

---

## 8. IMPLEMENTATION PLAN

### Phase 1: Critical Fixes (Week 1)
- [ ] Make PDF parsing async (run in executor)
- [ ] Fix synthesis LLM calls (invoke → ainvoke)
- [ ] Add PDF size/page guardrails
- [ ] Add basic timeout wrappers

### Phase 2: Monitoring (Week 2)
- [ ] Create ResourceMonitor utility
- [ ] Integrate into Analysis service
- [ ] Integrate into Synthesis service
- [ ] Add logging and metrics collection

### Phase 3: Optimization (Week 3)
- [ ] Wrap Supabase calls in executor
- [ ] Implement async file I/O
- [ ] Increase extraction concurrency
- [ ] Add memory usage guardrails

### Phase 4: Testing (Week 4)
- [ ] Create unit tests for each step
- [ ] Create integration tests
- [ ] Run load tests
- [ ] Document findings and recommendations

---

## 9. SUMMARY

### Current State:
- **Analysis Service**: 60% async, 40% blocking operations
- **Synthesis Service**: 40% async, 60% blocking operations
- **No resource monitoring**
- **No guardrails on file sizes or timeouts**

### After Implementation:
- **Analysis Service**: 95% async (only CPU-bound operations in executor)
- **Synthesis Service**: 95% async
- **Full resource monitoring and metrics**
- **Comprehensive guardrails and timeouts**
- **5-10x throughput improvement** (estimated)

### Key Metrics to Track:
- Documents processed per minute
- Memory usage per document
- CPU utilization pattern
- Error rate by stage
- End-to-end pipeline duration

