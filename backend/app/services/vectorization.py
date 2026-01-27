import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from supabase import create_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorizationService:
    """Service for generating embeddings and vector search using Supabase with pgvector"""

    def __init__(self):
        self._openai_client = None
        self._supabase = None

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for vectorization service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    @property
    def supabase(self):
        if self._supabase is None:
            if not settings.SUPABASE_URL:
                raise ValueError("SUPABASE_URL is required for vectorization service")
            if not settings.SUPABASE_KEY:
                raise ValueError("SUPABASE_KEY is required for vectorization service")

            self._supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return self._supabase

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI"""
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small", input=text.replace("\n", " ")
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    async def search_similar_content(
        self,
        query: str,
        project_id: str,
        match_threshold: float = 0.8,
        match_count: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar content using pgvector"""
        try:
            query_embedding = await self.generate_embedding(query)

            result = self.supabase.rpc(
                "match_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": match_threshold,
                    "match_count": match_count,
                    "project_filter": project_id,
                },
            ).execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error searching similar content: {e}")
            return []


# Global instance
vectorization_service = VectorizationService()
