# Spec: Single Unparseable Document Crashes Entire Project Analysis

## Problem

A single oversized or unparseable document causes the entire project analysis to fail with a 500 error, even when dozens of other documents have already been successfully parsed.

### Observed Behaviour

From production logs (2026-03-02), project `90f99980-04d8-4430-b9ee-9afd67bc213e`:

- ~30 documents parsed successfully over ~4 seconds
- The final document (`10.2799/0409819`, a 70.2MB PDF) exceeds the 50MB limit
- The entire project fails with HTTP 500 and is marked `status: "failed"` in the database
- All successfully parsed work is wasted

### Root Cause

There is a mismatch between the parser's **contract** and its **implementation**, and a missing `try/except` in the service layer's parsing loop.

**Step 1 — Parser says "skip" but raises an exception**

`parse.py:71-128` — `parse_saved_file` has a docstring that says:

```
Returns:
    ParsedText object or None if parsing fails or file should be skipped
```

But for two error paths, it raises `ParsingError` instead of returning `None`:

| Line | Trigger | Behaviour |
|---|---|---|
| 97 | PDF exceeds file size limit | `raise ParsingError(skip_reason)` |
| 123 | Parsing times out | `raise ParsingError(...)` |

These raises happen **outside** the general `except Exception` on line 126 that returns `None`, so they propagate uncaught.

**Step 2 — Service loop has no per-document error handling**

`service.py:214-258` — The parsing loop calls `parse_saved_file` without any `try/except`:

```python
for item in acquired:
    ...
    parsed = await parser.parse_saved_file(doc_id, item["file_path"])  # bare await
    if not parsed:       # only handles None returns
        skipped_count += 1
        continue
```

When `ParsingError` is raised, it immediately unwinds the `for` loop and exits `AnalysisService.run`.

**Step 3 — API layer catches it as a fatal error**

`projects.py:1077-1086` — The broad `except Exception` handler catches the `ParsingError`, marks the entire project as `failed`, and returns HTTP 500:

```python
except Exception as e:
    logger.error(f"Error running analysis for project {project_id}: {e}")
    vectorization_service.supabase.table("analysis_projects").update(
        {"status": "failed"}
    ).eq("id", project_id).execute()
    raise HTTPException(status_code=500, ...)
```

### Propagation Diagram

```
parse_saved_file (line 97)
  raises ParsingError ──────────────────────────┐
                                                │
service.py for-loop (line 219)                  │
  no try/except, loop aborts ◄──────────────────┘
  AnalysisService.run exits with ParsingError ──┐
                                                │
projects.py (line 1077)                         │
  except Exception catches it ◄─────────────────┘
  marks project "failed" in DB
  returns HTTP 500
```

## Affected Files

| File | Location | Issue |
|---|---|---|
| `backend/app/services/analysis/parse.py` | L95-97 | Raises `ParsingError` instead of returning `None` for oversized PDFs |
| `backend/app/services/analysis/parse.py` | L121-123 | Raises `ParsingError` instead of returning `None` for timeouts |
| `backend/app/services/analysis/service.py` | L219 | Bare `await` with no `try/except ParsingError` around individual documents |

## Solution

Fix in `parse.py` only. The parser's own docstring says it should return `None` when a file should be skipped. Make the implementation match the contract. No changes needed in `service.py` or `projects.py` because they already handle `None` correctly.

### Before (`parse.py:92-97`)

```python
if path.suffix.lower() == ".pdf":
    # Quick check: skip if file is too large
    should_skip, skip_reason = should_skip_large_pdf(file_size)
    if should_skip:
        logger.warning("Skipping PDF %s: %s", doc_id, skip_reason)
        raise ParsingError(skip_reason)
```

### After (`parse.py:92-97`)

```python
if path.suffix.lower() == ".pdf":
    # Quick check: skip if file is too large
    should_skip, skip_reason = should_skip_large_pdf(file_size)
    if should_skip:
        logger.warning("Skipping PDF %s: %s", doc_id, skip_reason)
        return None
```

### Before (`parse.py:121-123`)

```python
except asyncio.TimeoutError:
    logger.warning("Parsing timeout for %s after %.1fs", doc_id, timeout)
    raise ParsingError(f"Parsing timed out after {timeout:.0f} seconds")
```

### After (`parse.py:121-123`)

```python
except asyncio.TimeoutError:
    logger.warning("Parsing timeout for %s after %.1fs", doc_id, timeout)
    return None
```

### Why this is sufficient

- `service.py:220-227` already checks `if not parsed:` and increments `skipped_count` — no changes needed there.
- `projects.py` never sees the error — no changes needed there.
- The `ParsingError` class and the `except ParsingError: raise` on line 124-125 can remain for use by internal parsing code (`_parse_pdf`, `_parse_html`) where errors should still propagate to the `except Exception` on line 126, which already returns `None`.

### Expected Result After Fix

Using the same input that caused the failure:

1. 30+ documents parse successfully (unchanged)
2. `10.2799/0409819` (70.2MB) logs a warning and is skipped — `skipped_count` increments
3. The parsing loop completes normally
4. Extraction, vectorization, and all downstream steps proceed with the 30+ successfully parsed documents
5. Project completes with `status: "completed"` instead of `"failed"`
