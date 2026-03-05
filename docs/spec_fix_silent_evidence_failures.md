# Spec: Fix Silent Evidence Categorisation Failures

## Problem

When the LLM is classifying documents into evidence categories (e.g. "Systematic Review", "RCT"), a single failed LLM call (timeout, rate limit, API error) causes **all** categorisation results to be thrown away. The pipeline then silently continues, and the project appears "completed" with blank evidence category and strength fields.

This happens because:
1. Documents are sent to the LLM in batches of 25 via `asyncio.gather()`, which fails entirely if any single call fails.
2. The error is caught and swallowed — the code returns the unmodified CSV and carries on.

## Fix Overview

Two changes:
1. **Don't let one failure kill everything** — handle individual LLM call failures so the other 24/25 results survive. Retry failed calls before giving up.
2. **Don't pretend nothing happened** — log when documents fail categorisation (kept minimal — one summary line per run, not per document).

## Files to Change

### 1. `backend/app/utils/llm/batch_check.py`

This is the shared LLM batch processor used by both relevance checking and evidence categorisation.

**Change A: Add retry logic to `_invoke_llm`** (line 125)

Before:
```python
async def _invoke_llm(self, input_text: str, _id: str) -> Dict:
    start_time = datetime.now(tz=timezone.utc).isoformat()
    structured_llm = self.llm.with_structured_output(self.schema)
    tags = self.component_tags + [
        "component:batch_check.process",
        f"model:{self.model_name}",
    ]
    if self.policy_project_id:
        tags.append(f"project:{self.policy_project_id}")
    response = await structured_llm.ainvoke(
        input_text,
        config={...},
    )
    response = response.model_dump()
    response["id"] = _id
    response["timestamp"] = start_time
    response["model"] = self.model_name
    response["temperature"] = self.temperature

    return response
```

After:
```python
async def _invoke_llm(
    self, input_text: str, _id: str, max_retries: int = 2
) -> Optional[Dict]:
    start_time = datetime.now(tz=timezone.utc).isoformat()
    structured_llm = self.llm.with_structured_output(self.schema)
    tags = self.component_tags + [
        "component:batch_check.process",
        f"model:{self.model_name}",
    ]
    if self.policy_project_id:
        tags.append(f"project:{self.policy_project_id}")

    for attempt in range(1, max_retries + 1):
        try:
            response = await structured_llm.ainvoke(
                input_text,
                config={...},
            )
            response = response.model_dump()
            response["id"] = _id
            response["timestamp"] = start_time
            response["model"] = self.model_name
            response["temperature"] = self.temperature
            return response
        except Exception as e:
            if attempt < max_retries:
                logger.debug(
                    "LLM call failed for %s (attempt %d/%d): %s",
                    _id, attempt, max_retries, e,
                )
                await asyncio.sleep(1 * attempt)
            else:
                logger.debug(
                    "LLM call failed for %s after %d attempts: %s",
                    _id, max_retries, e,
                )
                return None
```

> Retry/failure details are `DEBUG` level — invisible in production, available if needed for debugging.

**Change B: Handle individual failures in `_process_batch`** (line 160)

Before:
```python
async def _process_batch(
    self, batch: List[str], batch_ids: List[str], prompt_template: str
) -> List[Dict]:
    tasks = []
    for idx, text_data in enumerate(batch):
        formatted_prompt = prompt_template.format(input=text_data)
        tasks.append(self._invoke_llm(formatted_prompt, batch_ids[idx]))

    return await asyncio.gather(*tasks)
```

After:
```python
async def _process_batch(
    self, batch: List[str], batch_ids: List[str], prompt_template: str
) -> List[Dict]:
    tasks = []
    for idx, text_data in enumerate(batch):
        formatted_prompt = prompt_template.format(input=text_data)
        tasks.append(self._invoke_llm(formatted_prompt, batch_ids[idx]))

    results = await asyncio.gather(*tasks)
    # Filter out None results (failed calls)
    return [r for r in results if r is not None]
```

> No logging here — the summary is logged once at the end in `process_text_data`.

**Change C: Single summary log in `process_text_data`** (line 170)

Before:
```python
async def process_text_data(
    self, text_data: Dict[str, str], batch_size: int = 10, sleep_time: float = 0.5
) -> None:
    prompt_template = self._get_prompt_template()
    processed_ids = self._load_processed_ids()
    text_data = {k: v for k, v in text_data.items() if k not in processed_ids}

    if not text_data:
        logger.info("All data has already been processed.")
        return

    _text_data = list(text_data.values())
    _ids = list(text_data.keys())

    num_batches = math.ceil(len(_text_data) / batch_size)
    for i in range(num_batches):
        logger.info(f"Processing batch {i + 1}/{num_batches}")
        start_idx = i * batch_size
        end_idx = start_idx + batch_size
        batch = _text_data[start_idx:end_idx]
        batch_ids = _ids[start_idx:end_idx]

        responses = await self._process_batch(batch, batch_ids, prompt_template)

        with open(self.output_path, "a") as f:
            for response in responses:
                f.write(json.dumps(response) + "\n")

        if i < num_batches - 1:
            await asyncio.sleep(sleep_time)
```

After:
```python
async def process_text_data(
    self, text_data: Dict[str, str], batch_size: int = 10, sleep_time: float = 0.5
) -> None:
    prompt_template = self._get_prompt_template()
    processed_ids = self._load_processed_ids()
    text_data = {k: v for k, v in text_data.items() if k not in processed_ids}

    if not text_data:
        logger.info("All data has already been processed.")
        return

    _text_data = list(text_data.values())
    _ids = list(text_data.keys())

    total_succeeded = 0
    num_batches = math.ceil(len(_text_data) / batch_size)
    for i in range(num_batches):
        logger.info(f"Processing batch {i + 1}/{num_batches}")
        start_idx = i * batch_size
        end_idx = start_idx + batch_size
        batch = _text_data[start_idx:end_idx]
        batch_ids = _ids[start_idx:end_idx]

        responses = await self._process_batch(batch, batch_ids, prompt_template)
        total_succeeded += len(responses)

        with open(self.output_path, "a") as f:
            for response in responses:
                f.write(json.dumps(response) + "\n")

        if i < num_batches - 1:
            await asyncio.sleep(sleep_time)

    total_failed = len(_text_data) - total_succeeded
    if total_failed:
        logger.warning(
            "Batch processing: %d/%d calls failed", total_failed, len(_text_data)
        )
```

> Only logs a WARNING when there are actual failures. Zero failures = no extra log line.

---

### 2. `backend/app/services/analysis/evidence/category.py`

**Change D: Replace silent swallow with one-line summary in `categorise_documents`** (line 251)

Before:
```python
try:
    results_df = await self._screen_batch(documents)
    if results_df.empty:
        logger.warning("Evidence categorisation returned no results")
        return references_csv_path

    df = self._merge_evidence_results(df, results_df)
    df.to_csv(references_csv_path, index=False)

    categorised = df["evidence_category"].notna().sum()
    logger.info(f"Categorised {categorised} documents")
    return references_csv_path

except Exception as e:
    logger.error(f"Evidence categorisation failed: {e}")
    return references_csv_path
```

After:
```python
try:
    results_df = await self._screen_batch(documents)
    if results_df.empty:
        logger.error(
            "Evidence categorisation: 0/%d succeeded (project %s)",
            len(documents), self.project_id,
        )
        return references_csv_path

    df = self._merge_evidence_results(df, results_df)
    df.to_csv(references_csv_path, index=False)

    categorised = df["evidence_category"].notna().sum()
    uncategorised = len(docs_to_process) - categorised
    if uncategorised:
        logger.warning(
            "Evidence categorisation: %d/%d succeeded (project %s)",
            categorised, len(docs_to_process), self.project_id,
        )
    else:
        logger.info(
            "Evidence categorisation: %d/%d succeeded (project %s)",
            categorised, len(docs_to_process), self.project_id,
        )
    return references_csv_path

except Exception as e:
    logger.error(
        "Evidence categorisation failed (project %s): %s",
        self.project_id, e,
    )
    return references_csv_path
```

> One line. Format: `Evidence categorisation: 37/40 succeeded (project abc-123)`. WARNING if any missing, INFO if all good, ERROR if total failure.

---

## Logging Summary

| Level | When | Example |
|-------|------|---------|
| INFO | All docs categorised successfully | `Evidence categorisation: 40/40 succeeded (project abc)` |
| WARNING | Some docs failed | `Evidence categorisation: 37/40 succeeded (project abc)` |
| ERROR | Total failure (0 results) | `Evidence categorisation: 0/40 succeeded (project abc)` |
| DEBUG | Individual retry details (production invisible) | `LLM call failed for doc_xyz (attempt 1/2): timeout` |

## What This Achieves

| Before | After |
|--------|-------|
| 1 failed LLM call loses all 25 results in a batch | Failed calls are retried once, and only that document's result is lost |
| Silent failure — no trace in logs | One summary line per run showing success/failure count |
| Project appears fully complete with blank fields | Project still completes, but logs make it obvious what's missing |

## What This Does NOT Change

- No database schema changes needed
- No API changes needed
- No frontend changes needed
- The pipeline still continues on partial failure (we don't crash the project)
- Relevance checking uses the same `batch_check.py` code, so it also benefits from the retry logic
