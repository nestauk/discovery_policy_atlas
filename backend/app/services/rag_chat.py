import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class RAGChatService:
    """Service for RAG-enhanced chat functionality over collected evidence"""

    def __init__(self):
        self._openai_client = None
        self._vectorization = None

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for RAG chat service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    @property
    def vectorization(self):
        if self._vectorization is None:
            from app.services.vectorization import vectorization_service

            self._vectorization = vectorization_service
        return self._vectorization

    async def generate_rag_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]],
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    ) -> str:
        """Generate a response using RAG over the collected evidence"""

        try:
            # Search for relevant documents (summaries only)
            relevant_docs = await self.vectorization.search_similar_content(
                query=user_message,
                project_id=project_id,
                match_threshold=0.7,
                match_count=5,  # Max 5 since we only have 5 documents total
            )

            if not relevant_docs:
                return self._no_evidence_response()

            # Get full document information including links
            docs_with_links = await self._enrich_documents_with_links(
                relevant_docs, project_id
            )

            # Build context from relevant documents
            context = self._build_context_from_documents(docs_with_links)

            # Generate response using OpenAI with RAG context
            response = await self._generate_openai_response(
                user_message, conversation_history, context, docs_with_links
            )

            return response

        except Exception as e:
            logger.error(f"Error in RAG response generation: {e}")
            return "I'm sorry, I encountered an error while searching through the evidence. Please try again."

    def _build_context_from_documents(self, chunks: List[Dict[str, Any]]) -> str:
        """Build context string from relevant document summaries"""
        context_parts = []

        for i, chunk in enumerate(chunks, 1):
            similarity = chunk.get("similarity", 0)
            content = chunk.get("content", "")
            title = chunk.get("document_title", "Unknown Document")

            # Since we only use summary chunks now, we can simplify the context
            chunk_context = f"[Document {i}] {title}\n"
            chunk_context += f"Content: {content}\n"
            chunk_context += f"Relevance Score: {similarity:.2f}\n"

            context_parts.append(chunk_context)

        return "\n" + "=" * 50 + "\n".join(context_parts)

    async def _enrich_documents_with_links(
        self, chunks: List[Dict[str, Any]], project_id: str
    ) -> List[Dict[str, Any]]:
        """Enrich chunks with full document information including links"""
        enriched_chunks = []

        # Get unique document IDs
        document_ids = list(
            set(
                chunk.get("document_id") for chunk in chunks if chunk.get("document_id")
            )
        )

        # Fetch document details from Supabase
        document_details = {}
        if document_ids:
            try:
                result = (
                    self.vectorization.supabase.table("documents")
                    .select(
                        "id, title, authors, doi, overton_url, source_country, published_date"
                    )
                    .in_("id", document_ids)
                    .execute()
                )

                for doc in result.data:
                    document_details[doc["id"]] = doc
            except Exception as e:
                logger.error(f"Error fetching document details: {e}")

        # Enrich chunks with document details
        for chunk in chunks:
            enriched_chunk = chunk.copy()
            doc_id = chunk.get("document_id")

            if doc_id and doc_id in document_details:
                doc_details = document_details[doc_id]
                enriched_chunk.update(
                    {
                        "document_authors": doc_details.get("authors", []),
                        "document_doi": doc_details.get("doi"),
                        "document_overton_url": doc_details.get("overton_url"),
                        "document_source_country": doc_details.get("source_country"),
                        "document_published_date": doc_details.get("published_date"),
                    }
                )

            enriched_chunks.append(enriched_chunk)

        return enriched_chunks

    async def _generate_openai_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, Any]],
        context: str,
        docs_with_links: List[Dict[str, Any]],
    ) -> str:
        """Generate response using OpenAI with RAG context"""

        # Build conversation history for context
        conversation_context = ""
        if conversation_history:
            recent_messages = conversation_history[-6:]  # Last 6 messages for context
            for msg in recent_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content:
                    conversation_context += f"{role.capitalize()}: {content}\n"

        system_prompt = f"""You are a policy research assistant that helps users understand and analyze collected evidence. 

You have access to a focused collection of the top 5 most relevant policy documents that have been gathered and analyzed using semantic search and AI screening. Use this evidence to answer the user's questions.

IMPORTANT GUIDELINES:
1. Base your answers ONLY on the evidence provided below (5 high-quality documents)
2. If the evidence doesn't contain relevant information, say so clearly
3. Always cite the specific documents when referencing information using [Document 1], [Document 2], etc.
4. Provide nuanced, evidence-based analysis from these curated sources
5. Highlight key findings and policy implications
6. Reference the relevance scores when discussing evidence quality
7. Keep responses concise but comprehensive
8. These documents were selected as the most relevant, so they should contain good evidence for most policy questions

AVAILABLE EVIDENCE (Top 5 Documents):
{context}

RECENT CONVERSATION:
{conversation_context}

When citing documents, use the format: [Document 1], [Document 2], etc. referring to the numbered documents in the evidence above.
"""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=1000,
            )

            ai_response = response.choices[0].message.content

            # Add citations with links
            citations_section = self._build_citations_section(docs_with_links)
            if citations_section:
                ai_response += f"\n\n{citations_section}"

            return ai_response

        except Exception as e:
            logger.error(f"OpenAI API error in RAG chat: {e}")
            return "I'm sorry, I encountered an error while generating a response. Please try again."

    def _build_citations_section(self, docs_with_links: List[Dict[str, Any]]) -> str:
        """Build a references section with clickable links"""
        if not docs_with_links:
            return ""

        citations = []
        seen_documents = set()  # Track unique documents to avoid duplicates

        for i, doc in enumerate(docs_with_links, 1):
            document_id = doc.get("document_id")
            if document_id in seen_documents:
                continue
            seen_documents.add(document_id)

            title = doc.get("document_title", "Unknown Document")
            authors = doc.get("document_authors", [])
            source_country = doc.get("document_source_country")
            published_date = doc.get("document_published_date")
            doi = doc.get("document_doi")
            overton_url = doc.get("document_overton_url")

            # Format authors
            authors_str = ", ".join(authors) if authors else "Unknown authors"

            # Format date
            date_str = ""
            if published_date:
                try:
                    if isinstance(published_date, str):
                        from datetime import datetime

                        date_obj = datetime.fromisoformat(
                            published_date.replace("Z", "+00:00")
                        )
                        date_str = f" ({date_obj.year})"
                    else:
                        date_str = f" ({published_date.year})"
                except (ValueError, AttributeError, TypeError):
                    pass

            # Format country
            country_str = f" [{source_country}]" if source_country else ""

            # Build citation with link
            citation = f"**Document {i}:** {title}{date_str}{country_str}"
            if authors_str != "Unknown authors":
                citation += f"\n*Authors: {authors_str}*"

            # Add link (prefer DOI, fallback to Overton URL)
            link_url = None
            link_text = None

            if doi:
                if doi.startswith("http"):
                    link_url = doi
                else:
                    link_url = f"https://doi.org/{doi}"
                link_text = "View Paper (DOI)"
            elif overton_url:
                link_url = overton_url
                link_text = "View Document (Overton)"

            if link_url and link_text:
                citation += f"\n🔗 [{link_text}]({link_url})"

            citations.append(citation)

        if citations:
            return "## 📚 References\n\n" + "\n\n".join(citations)

        return ""

    def _no_evidence_response(self) -> str:
        """Response when no relevant evidence is found"""
        return """I don't have any relevant evidence in my knowledge base to answer that question. 

This could mean:
1. The search results haven't been processed yet
2. Your question is outside the scope of the collected evidence
3. You might want to refine your search or collect additional evidence

Try asking about topics related to your original research question, or consider running a new search with different terms."""

    async def check_evidence_availability(
        self, project_id: str = "test_project"
    ) -> Dict[str, Any]:
        """Check if evidence is available for the project"""
        try:
            documents = self.vectorization.get_project_documents(project_id)
            return {
                "has_evidence": len(documents) > 0,
                "document_count": len(documents),
                "documents": [
                    {
                        "title": doc.get("title", ""),
                        "source_country": doc.get("source_country", ""),
                        "confidence": doc.get("confidence", 0),
                    }
                    for doc in documents[:5]  # First 5 for preview
                ],
            }
        except Exception as e:
            logger.error(f"Error checking evidence availability: {e}")
            return {"has_evidence": False, "document_count": 0, "documents": []}


# Global instance
rag_chat_service = RAGChatService()
