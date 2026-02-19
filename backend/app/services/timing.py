"""Persist pipeline stage timings to the pipeline_timings Supabase table."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_supabase():
    """Get a Supabase client (reuses the pattern from logbook.py)."""
    from app.core.config import settings
    from supabase import create_client

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def persist_timing(
    project_id: str,
    pipeline_type: str,
    stage_name: str,
    duration_seconds: float,
    document_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert a single timing row.

    Failures are logged as warnings and never propagated — timing is
    best-effort and must not break the pipeline.
    """
    try:
        row = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "pipeline_type": pipeline_type,
            "stage_name": stage_name,
            "duration_seconds": duration_seconds,
            "document_count": document_count,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _get_supabase().table("pipeline_timings").insert(row).execute()
    except Exception as e:
        logger.warning(
            "Failed to persist timing for %s/%s: %s", pipeline_type, stage_name, e
        )


def persist_timings_batch(
    project_id: str,
    pipeline_type: str,
    timings: List[Dict[str, Any]],
) -> None:
    """Batch-insert multiple timing rows.

    Each item in *timings* must have at least ``stage_name`` and
    ``duration_seconds``.  Optional keys: ``document_count``, ``metadata``.

    A no-op when *timings* is empty.
    """
    if not timings:
        return

    try:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "pipeline_type": pipeline_type,
                "stage_name": t["stage_name"],
                "duration_seconds": t["duration_seconds"],
                "document_count": t.get("document_count"),
                "metadata": t.get("metadata", {}),
                "created_at": now,
            }
            for t in timings
        ]
        _get_supabase().table("pipeline_timings").insert(rows).execute()
    except Exception as e:
        logger.warning("Failed to persist batch timings for %s: %s", pipeline_type, e)


def get_timings_for_project(
    project_id: str,
    pipeline_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return all timings for a project, ordered by created_at."""
    query = (
        _get_supabase()
        .table("pipeline_timings")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at")
    )
    if pipeline_type:
        query = query.eq("pipeline_type", pipeline_type)
    result = query.execute()
    return result.data or []
