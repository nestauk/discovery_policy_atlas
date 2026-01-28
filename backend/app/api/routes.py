from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import io
from datetime import datetime
from app.core.auth import get_current_user, CurrentUser
from app.services.download import download_service
from app.services.analysis.evidence.category import get_evidence_categories_for_api
import logging

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/api/config/evidence-categories")
async def get_evidence_categories():
    """Get evidence category configuration for the frontend.

    Returns all evidence categories with their display properties (colors,
    short names, scores, ranks) from the single source of truth in the backend.
    """
    return {"categories": get_evidence_categories_for_api()}


@router.get("/api/download/{download_key}")
async def download_csv(
    download_key: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Download search results as CSV"""
    # Get DataFrame from cache
    result = download_service.get_dataframe(download_key, current_user.user_id)

    if result is None:
        return JSONResponse(
            status_code=404, content={"error": "Download not found or expired"}
        )

    df, cache_entry = result

    # Convert DataFrame to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    # Create filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{cache_entry.filename_prefix}_{timestamp}.csv"

    # Return as streaming response
    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
