import asyncio
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from supabase import create_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorizationService:
    """Service for generating embeddings and storing documents in Supabase with pgvector"""

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

    async def store_document(
        self,
        paper: Dict[str, Any],
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    ) -> Optional[str]:
        """Store a document and its sections in Supabase"""
        try:
            # Prepare document data
            document_data = {
                "project_id": project_id,
                "external_id": str(paper.get("id", "")),
                "title": paper.get("title", ""),
                "authors": paper.get("authors", [])
                if isinstance(paper.get("authors"), list)
                else [paper.get("authors", "")],
                "abstract": paper.get("abstract", ""),
                "content": paper.get("content", ""),
                "source_type": "overton",  # Default for now
                "source_country": paper.get("source_country"),
                # Prefer explicit publication_date, then published_on
                "published_date": paper.get("publication_date")
                or paper.get("published_on"),
                "doi": paper.get("doi"),
                "overton_url": paper.get("overton_url"),
                "confidence": paper.get("confidence", 0.0),
                "relevance_reason": paper.get("relevance_reason", ""),
                "top_line": paper.get("top_line", ""),
                "metadata": {
                    "is_relevant": paper.get("is_relevant", True),
                    "cited_by_count": paper.get("cited_by_count", 0),
                    "publication_year": paper.get("publication_year"),
                    # Newly extracted structured fields
                    "key_facts": paper.get("key_facts", [])
                    if isinstance(paper.get("key_facts"), list)
                    else (
                        []
                        if paper.get("key_facts") in (None, "")
                        else [paper.get("key_facts")]
                    ),
                    "policy_recommendations": paper.get("policy_recommendations", [])
                    if isinstance(paper.get("policy_recommendations"), list)
                    else (
                        []
                        if paper.get("policy_recommendations") in (None, "")
                        else [paper.get("policy_recommendations")]
                    ),
                },
            }

            # Insert or update document
            result = (
                self.supabase.table("documents")
                .upsert(document_data, on_conflict="project_id,external_id,source_type")
                .execute()
            )

            if not result.data:
                logger.error("Failed to insert document")
                return None

            document_id = result.data[0]["id"]
            logger.info(f"Stored document {document_id}")

            # Create document chunks for embedding
            await self._create_document_chunks(document_id, paper, project_id)

            return document_id

        except Exception as e:
            logger.error(f"Error storing document: {e}")
            return None

    async def _create_document_chunks(
        self, document_id: str, paper: Dict[str, Any], project_id: str
    ):
        """Create embeddings for document summaries only"""
        chunks_to_embed = []

        # Create a comprehensive summary section (only chunk type we'll use)
        summary_parts = []
        if paper.get("title"):
            summary_parts.append(f"Title: {paper['title']}")
        if paper.get("top_line"):
            summary_parts.append(f"Key Finding: {paper['top_line']}")
        if paper.get("relevance_reason"):
            summary_parts.append(f"Relevance: {paper['relevance_reason']}")
        if paper.get("abstract"):
            # Truncate abstract if too long
            abstract = (
                paper["abstract"][:1000] + "..."
                if len(paper["abstract"]) > 1000
                else paper["abstract"]
            )
            summary_parts.append(f"Abstract: {abstract}")

        # Only create summary chunk for vectorization
        if summary_parts:
            chunks_to_embed.append(
                {
                    "content": "\n\n".join(summary_parts),
                    "chunk_type": "summary",
                    "chunk_index": 0,
                }
            )

        # Generate embeddings and store chunks (only summary)
        for chunk in chunks_to_embed:
            try:
                embedding = await self.generate_embedding(chunk["content"])

                chunk_data = {
                    "document_id": document_id,
                    "project_id": project_id,
                    "content": chunk["content"],
                    "chunk_type": chunk["chunk_type"],
                    "chunk_index": chunk["chunk_index"],
                    "embedding": embedding,
                    "token_count": len(chunk["content"].split()),
                }

                self.supabase.table("chunks").insert(chunk_data).execute()
                logger.info(f"Created chunk: {chunk['chunk_type']}")

            except Exception as e:
                logger.error(f"Error creating chunk {chunk['chunk_type']}: {e}")

    async def store_search_results(
        self,
        papers: List[Dict[str, Any]],
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    ) -> Dict[str, Any]:
        """Store multiple papers from search results"""
        stored_count = 0
        failed_count = 0

        for paper in papers:
            try:
                document_id = await self.store_document(paper, project_id)
                if document_id:
                    stored_count += 1
                else:
                    failed_count += 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error storing paper {paper.get('id', 'unknown')}: {e}")
                failed_count += 1

        return {
            "stored_count": stored_count,
            "failed_count": failed_count,
            "total_count": len(papers),
        }

    async def search_similar_content(
        self,
        query: str,
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        match_threshold: float = 0.8,
        match_count: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar content using pgvector"""
        try:
            # Generate embedding for query
            query_embedding = await self.generate_embedding(query)

            # Use the PostgreSQL function for similarity search
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

    def get_project_documents(
        self, project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    ) -> List[Dict[str, Any]]:
        """Get all documents for a project"""
        try:
            result = (
                self.supabase.table("documents")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting project documents: {e}")
            return []


# Global instance
vectorization_service = VectorizationService()
