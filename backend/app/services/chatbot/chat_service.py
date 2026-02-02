"""
Simple RAG chatbot service for v2 analysis projects.
"""

import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.vectorization import vectorization_service
from .models import ChatRequest, ChatResponse, ChatMessage, DocumentReference

logger = logging.getLogger(__name__)


class ChatbotService:
    """Simple RAG chatbot service for analysis projects."""

    def __init__(self):
        self._openai_client = None

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for chatbot service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def chat(self, project_id: str, request: ChatRequest) -> ChatResponse:
        """Generate a chat response using RAG over project evidence."""
        try:
            # Search for relevant chunks
            relevant_chunks = await self._search_relevant_chunks(
                project_id, request.message
            )

            if not relevant_chunks:
                return ChatResponse(
                    message="I don't have any relevant evidence in this project to answer that question. Try asking about topics related to your research question or search for more evidence.",
                    references=[],
                )

            # Get neighboring chunks for better context
            enriched_chunks = await self._get_chunks_with_neighbors(
                project_id, relevant_chunks
            )

            # Get document details for references
            chunks_with_docs = await self._enrich_with_document_details(enriched_chunks)

            # Build context for LLM
            context = self._build_context(chunks_with_docs)

            # Generate response using OpenAI
            response_text = await self._generate_response(
                request.message, context, request.recent_messages
            )

            # Build document references
            references = self._build_references(chunks_with_docs)

            return ChatResponse(message=response_text, references=references)

        except Exception as e:
            logger.error(f"Error in chatbot service: {e}")
            return ChatResponse(
                message="I'm sorry, I encountered an error while processing your question. Please try again.",
                references=[],
            )

    async def _search_relevant_chunks(
        self, project_id: str, query: str, max_chunks: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector similarity."""
        return await vectorization_service.search_similar_content(
            query=query,
            project_id=project_id,
            match_threshold=0.51,
            match_count=max_chunks,
        )

    async def _get_chunks_with_neighbors(
        self, project_id: str, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fetch neighboring chunks for additional context."""
        if not chunks:
            return []

        enriched_chunks = []
        document_chunk_map = {}

        # Group chunks by document
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id:
                if doc_id not in document_chunk_map:
                    document_chunk_map[doc_id] = []
                document_chunk_map[doc_id].append(chunk)

        # For each document, fetch neighboring chunks
        for doc_id, doc_chunks in document_chunk_map.items():
            try:
                # Get all chunk indices for this document
                chunk_indices = [c.get("chunk_index", 0) for c in doc_chunks]
                min_index = min(chunk_indices)
                max_index = max(chunk_indices)

                # Expand range to include neighbors (±1 chunk on each side)
                expanded_min = max(0, min_index - 1)
                expanded_max = max_index + 1

                # Fetch all chunks in the expanded range
                result = (
                    vectorization_service.supabase.table("chunks")
                    .select("*")
                    .eq("document_id", doc_id)
                    .gte("chunk_index", expanded_min)
                    .lte("chunk_index", expanded_max)
                    .order("chunk_index")
                    .execute()
                )

                if result.data:
                    enriched_chunks.extend(result.data)
                else:
                    # Fallback to original chunks if query fails
                    enriched_chunks.extend(doc_chunks)

            except Exception as e:
                logger.warning(f"Failed to fetch neighbors for document {doc_id}: {e}")
                # Fallback to original chunks
                enriched_chunks.extend(doc_chunks)

        return enriched_chunks

    async def _enrich_with_document_details(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enrich chunks with document metadata."""
        if not chunks:
            return []

        # Get unique document IDs
        document_ids = list(
            set(c.get("document_id") for c in chunks if c.get("document_id"))
        )

        # Fetch document details from analysis_documents table
        # Note: document_ids are now UUIDs from analysis_documents.id
        document_details = {}
        if document_ids:
            try:
                result = (
                    vectorization_service.supabase.table("analysis_documents")
                    .select(
                        "id, doc_id, title, authors, doi, overton_url, source_country, year, published_on"
                    )
                    .in_("id", document_ids)
                    .execute()
                )

                for doc in result.data:
                    document_details[doc["id"]] = doc
            except Exception as e:
                logger.error(f"Error fetching document details: {e}")

        # Enrich chunks with document details
        enriched_chunks = []
        for chunk in chunks:
            enriched_chunk = chunk.copy()
            doc_id = chunk.get("document_id")
            if doc_id and doc_id in document_details:
                doc_details = document_details[doc_id]

                # Handle published date - prefer published_on, fallback to year
                published_date = doc_details.get("published_on")
                if not published_date and doc_details.get("year"):
                    published_date = f"{doc_details.get('year')}-01-01"

                enriched_chunk.update(
                    {
                        "document_title": doc_details.get("title", ""),
                        "document_authors": doc_details.get("authors", []),
                        "document_doi": doc_details.get("doi"),
                        "document_overton_url": doc_details.get("overton_url"),
                        "document_source_country": doc_details.get("source_country"),
                        "document_published_date": published_date,
                        "document_year": doc_details.get("year"),
                    }
                )
            enriched_chunks.append(enriched_chunk)

        return enriched_chunks

    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Build context string from chunks for the LLM."""
        if not chunks:
            return ""

        context_parts = []

        # Group chunks by document for better organization
        docs = {}
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id not in docs:
                docs[doc_id] = {
                    "title": chunk.get("document_title", "Unknown Document"),
                    "chunks": [],
                }
            docs[doc_id]["chunks"].append(chunk)

        # Build context by document
        for i, (doc_id, doc_info) in enumerate(docs.items(), 1):
            doc_context = f"\n--- DOCUMENT {i}: {doc_info['title']} ---\n"

            # Sort chunks by index for coherent reading
            sorted_chunks = sorted(
                doc_info["chunks"], key=lambda x: x.get("chunk_index", 0)
            )

            for chunk in sorted_chunks:
                chunk_type = chunk.get("chunk_type", "content")
                content = chunk.get("content", "")
                doc_context += f"\n[{chunk_type.upper()}]: {content}\n"

            context_parts.append(doc_context)

        return "\n".join(context_parts)

    async def _generate_response(
        self,
        user_message: str,
        context: str,
        recent_messages: Optional[List[ChatMessage]] = None,
    ) -> str:
        """Generate response using OpenAI."""

        # Build conversation history
        conversation_context = ""
        if recent_messages:
            for msg in recent_messages[-5:]:  # Last 5 messages for context
                role = "User" if msg.role == "user" else "Assistant"
                conversation_context += f"{role}: {msg.content}\n"

        system_prompt = f"""You are a policy research assistant that helps users understand evidence from academic documents and policy research.

You have access to relevant excerpts from research documents. Use this evidence to answer the user's questions accurately and helpfully.

IMPORTANT GUIDELINES:
1. Base your answers ONLY on the evidence provided below
2. Always cite specific documents when referencing information using [Document 1], [Document 2], etc.
3. If the evidence doesn't contain relevant information, say so clearly
4. Provide nuanced, evidence-based analysis
5. Keep responses concise but comprehensive
6. Focus on policy implications and actionable insights
7. When multiple documents discuss the same topic, synthesize the information

AVAILABLE EVIDENCE:
{context}

{f"RECENT CONVERSATION:{conversation_context}" if conversation_context else ""}

Answer the user's question based on this evidence."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=1000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return (
                "I encountered an error while generating a response. Please try again."
            )

    def _build_references(
        self, chunks: List[Dict[str, Any]]
    ) -> List[DocumentReference]:
        """Build document references from chunks."""
        references = []
        seen_docs = set()

        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)

                # Build URL (prefer DOI, fallback to Overton URL)
                url = None
                doi = chunk.get("document_doi")
                overton_url = chunk.get("document_overton_url")

                if doi:
                    url = (
                        f"https://doi.org/{doi}" if not doi.startswith("http") else doi
                    )
                elif overton_url:
                    url = overton_url

                references.append(
                    DocumentReference(
                        document_id=doc_id,
                        title=chunk.get("document_title", "Unknown Document"),
                        authors=chunk.get("document_authors"),
                        doi=doi,
                        url=url,
                        chunk_type=chunk.get("chunk_type"),
                        published_date=chunk.get("document_published_date"),
                        year=chunk.get("document_year"),
                    )
                )

        return references


# Global instance
chatbot_service = ChatbotService()
