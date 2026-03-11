import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from app.core.config import settings
import app.core.database as db

logger = logging.getLogger(__name__)


class VectorizationService:
    """Service for generating embeddings and vector search using pgvector."""

    def __init__(self):
        self._openai_client = None

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for vectorization service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI."""
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
        """Search for similar content using pgvector."""
        try:
            query_embedding = await self.generate_embedding(query)
            embedding_str = db.fmt_vector(query_embedding)

            rows = db.fetch(
                "SELECT * FROM match_chunks(%s::vector, %s, %s, %s::text)",
                [embedding_str, match_threshold, match_count, project_id],
            )
            return rows
        except Exception as e:
            logger.error(f"Error searching similar content: {e}")
            return []


# Global instance
vectorization_service = VectorizationService()
