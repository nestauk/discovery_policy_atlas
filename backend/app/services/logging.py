import logging
from typing import Optional
from supabase import acreate_client, AsyncClient
from app.core.config import settings
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class LoggingService:
    def __init__(self):
        self._supabase: Optional[AsyncClient] = None

    async def _ensure_supabase(self) -> Optional[AsyncClient]:
        """Ensure Supabase async client is initialized."""
        if self._supabase is None:
            if settings.SUPABASE_URL and settings.SUPABASE_KEY:
                try:
                    self._supabase = await acreate_client(
                        settings.SUPABASE_URL, settings.SUPABASE_KEY
                    )
                    logger.info("Supabase async client initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")
                    self._supabase = None
            else:
                logger.warning(
                    "Supabase credentials not configured - logging will be disabled"
                )
        return self._supabase

    async def log_search(
        self, project_id: str, search_query: str, user_id: str
    ) -> Optional[str]:
        """
        Log a search query to Supabase

        Args:
            project_id: The project ID (placeholder for now)
            search_query: The user's search query after refinement
            user_id: The Clerk user ID

        Returns:
            search_id: The generated search ID, or None if logging failed
        """
        supabase = await self._ensure_supabase()
        if not supabase:
            logger.warning("Supabase not configured - skipping log")
            return None

        try:
            search_id = str(uuid.uuid4())

            # Prepare the data to insert
            search_data = {
                "search_id": search_id,
                "project_id": project_id,
                "search_query": search_query,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
            }

            # Insert into the searches table
            result = await supabase.table("searches").insert(search_data).execute()  # noqa: F841

            logger.info(
                f"Successfully logged search with ID: {search_id} for user: {user_id}"
            )
            return search_id

        except Exception as e:
            logger.error(f"Failed to log search to Supabase: {e}")
            return None

    async def get_search_history(self, project_id: str, limit: int = 10):
        """
        Get search history for a project

        Args:
            project_id: The project ID
            limit: Maximum number of searches to return

        Returns:
            List of search records
        """
        supabase = await self._ensure_supabase()
        if not supabase:
            logger.warning("Supabase not configured - cannot fetch history")
            return []

        try:
            result = (
                await supabase.table("searches")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            return result.data

        except Exception as e:
            logger.error(f"Failed to fetch search history: {e}")
            return []


# Create a global instance
logging_service = LoggingService()
