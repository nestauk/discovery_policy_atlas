import logging
from typing import Optional
from supabase import create_client, Client
from app.core.config import settings
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class LoggingService:
    def __init__(self):
        self.supabase: Optional[Client] = None
        self._initialize_supabase()

    def _initialize_supabase(self):
        """Initialize Supabase client if credentials are available"""
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            try:
                self.supabase = create_client(
                    settings.SUPABASE_URL, settings.SUPABASE_KEY
                )
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.supabase = None
        else:
            logger.warning(
                "Supabase credentials not configured - logging will be disabled"
            )

    async def log_search(self, project_id: str, search_query: str) -> Optional[str]:
        """
        Log a search query to Supabase

        Args:
            project_id: The project ID (placeholder for now)
            search_query: The user's search query after refinement

        Returns:
            search_id: The generated search ID, or None if logging failed
        """
        if not self.supabase:
            logger.warning("Supabase not configured - skipping log")
            return None

        try:
            search_id = str(uuid.uuid4())

            # Prepare the data to insert
            search_data = {
                "search_id": search_id,
                "project_id": project_id,
                "search_query": search_query,
                "created_at": datetime.utcnow().isoformat(),
            }

            # Insert into the searches table
            result = self.supabase.table("searches").insert(search_data).execute()  # noqa: F841

            logger.info(f"Successfully logged search with ID: {search_id}")
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
        if not self.supabase:
            logger.warning("Supabase not configured - cannot fetch history")
            return []

        try:
            result = (
                self.supabase.table("searches")
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
