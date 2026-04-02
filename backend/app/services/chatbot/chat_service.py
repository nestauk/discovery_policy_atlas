"""
Simple RAG chatbot service for v2 analysis projects.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Callable

from openai import AsyncOpenAI
from app.core.config import settings
from app.services.vectorization import vectorization_service
from .models import ChatRequest, ChatResponse, DocumentReference
from .parliament import search_parliament

logger = logging.getLogger(__name__)


MAX_AGENT_ITERATIONS = 5

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_project_evidence",
            "description": "Search the project's collected research documents and policy evidence for information relevant to the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant evidence.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_parliament",
            "description": "Search UK Parliament Hansard records including debates, written statements, written answers, and individual contributions. The search is keyword-based — use short terms (1-3 words) rather than full sentences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query for parliamentary records.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date filter in YYYY-MM-DD format.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date filter in YYYY-MM-DD format.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


class ChatbotService:
    """Simple RAG chatbot service for analysis projects."""

    def __init__(self):
        self._openai_client = None
        self._last_evidence_chunks: List[Dict[str, Any]] = []
        self._last_parliament_items: List[Dict[str, Any]] = []
        self._ordered_references: List[DocumentReference] = []
        self._evidence_reference_numbers: Dict[str, int] = {}
        self._parliament_reference_numbers: Dict[str, int] = {}

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for chatbot service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def chat(self, project_id: str, request: ChatRequest) -> ChatResponse:
        """Generate a chat response using tool-calling agent loop."""
        self._last_evidence_chunks = []
        self._last_parliament_items = []
        self._reset_reference_state()
        tool_handlers = self._build_tool_handlers(project_id)

        project_title = await self._get_project_title(project_id)

        # Build messages
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": self._build_system_prompt(project_title),
            },
        ]

        # Add conversation history
        if request.recent_messages:
            for msg in request.recent_messages[-5:]:
                messages.append({"role": msg.role.value, "content": msg.content})

        messages.append({"role": "user", "content": request.message})

        # Run agent loop
        final_message = await self._run_agent_loop(messages, tool_handlers)

        references = self._get_ordered_references()
        if not references:
            references = self._build_references(self._last_evidence_chunks)
            references.extend(
                self._build_parliament_references(self._last_parliament_items)
            )

        return ChatResponse(
            message=final_message.content
            or "I wasn't able to generate a response. Please try again.",
            references=references,
        )

    def _reset_reference_state(self) -> None:
        """Reset reference ordering for a new chat turn."""
        self._ordered_references = []
        self._evidence_reference_numbers = {}
        self._parliament_reference_numbers = {}

    def _get_ordered_references(self) -> List[DocumentReference]:
        """Return references in the same order used for [Document N] citations."""
        return list(self._ordered_references)

    def _build_system_prompt(self, project_title: Optional[str] = None) -> str:
        """Build system prompt for the tool-calling agent."""
        project_context = ""
        if project_title:
            project_context = f"\nPROJECT CONTEXT:\nThis project is about: {project_title}\nUse this topic to craft specific, relevant search queries for both tools. For example, search for the policy topic by name rather than generic terms like 'top interventions'.\n"

        return f"""You are a policy research assistant that helps users understand evidence from academic documents and policy research.

You have access to tools to search for information. Use them to find relevant evidence before answering.
{project_context}
TOOLS:
- search_project_evidence: Search the project's collected research documents. Use this first for most questions.
- search_parliament: Search UK Parliament Hansard records (debates, written statements, written answers, contributions). Use short keyword queries (1-3 terms) — the search is keyword-based, not semantic. Use this when the user asks about parliamentary activity, political feasibility, or government positions.

GUIDELINES:
1. Always search for evidence before answering — do not answer from memory alone
2. Cite specific documents when referencing information using [Document 1], [Document 2], etc.
3. If no relevant evidence is found, say so clearly
4. Provide nuanced, evidence-based analysis
5. Keep responses concise but comprehensive
6. Focus on policy implications and actionable insights
7. When multiple sources discuss the same topic, synthesize the information
8. When searching, use specific policy topic terms rather than generic phrases"""

    async def _search_relevant_chunks(
        self, project_id: str, query: str, max_chunks: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector similarity."""
        retrieval_query = await self._build_retrieval_query(project_id, query)

        return await vectorization_service.search_similar_content(
            query=retrieval_query,
            project_id=project_id,
            match_threshold=0.51,
            match_count=max_chunks,
            raise_on_error=True,
        )

    async def _build_retrieval_query(self, project_id: str, query: str) -> str:
        """Anchor vague questions with the project title before vector search."""
        project_title = await self._get_project_title(project_id)
        if not project_title:
            return query

        return f"Project: {project_title}\nQuestion: {query}"

    async def _get_project_title(self, project_id: str) -> Optional[str]:
        """Fetch the project title used to anchor retrieval queries."""
        try:
            result = (
                vectorization_service.supabase.table("analysis_projects")
                .select("title")
                .eq("id", project_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch project title for retrieval query %s: %s",
                project_id,
                exc,
            )
            return None

        if not result.data:
            return None

        title = result.data[0].get("title")
        if not isinstance(title, str):
            return None

        title = title.strip()
        return title or None

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

    def _build_context(
        self,
        chunks: List[Dict[str, Any]],
        document_numbers: Optional[Dict[str, int]] = None,
    ) -> str:
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
            doc_number = document_numbers.get(doc_id, i) if document_numbers else i
            doc_context = f"\n--- DOCUMENT {doc_number}: {doc_info['title']} ---\n"

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

    async def _run_agent_loop(
        self,
        messages: List[Dict[str, Any]],
        tool_handlers: Dict[str, Callable],
    ) -> Any:
        """Run the tool-calling agent loop. Returns the final assistant message."""
        for iteration in range(MAX_AGENT_ITERATIONS):
            logger.info("[chatbot] Agent loop iteration %d", iteration + 1)
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.7,
                max_tokens=1500,
            )
            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                logger.info(
                    "[chatbot] Final response (%d chars): %s",
                    len(assistant_message.content or ""),
                    (assistant_message.content or "")[:200],
                )
                return assistant_message

            # Append assistant message (with tool_calls) to conversation
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ],
                }
            )

            # Execute each tool call
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                logger.info(
                    "[chatbot] Tool call: %s(%s)",
                    tool_name,
                    tool_call.function.arguments,
                )
                handler = tool_handlers.get(tool_name)

                if handler is None:
                    tool_result = f"Error: Unknown tool '{tool_name}'"
                else:
                    try:
                        kwargs = json.loads(tool_call.function.arguments)
                        tool_result = await handler(**kwargs)
                    except Exception as exc:
                        logger.warning("Tool %s failed: %s", tool_name, exc)
                        tool_result = f"Error executing {tool_name}: {exc}"

                logger.info(
                    "[chatbot] Tool result (%d chars): %s",
                    len(str(tool_result)),
                    str(tool_result)[:300],
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(tool_result),
                    }
                )

        # Hit iteration cap — return the last assistant message
        return assistant_message

    def _build_tool_handlers(self, project_id: str) -> Dict[str, Callable]:
        """Build tool handler dict for the agent loop."""

        async def _handle_search_evidence(query: str) -> str:
            chunks = await self._search_relevant_chunks(project_id, query)
            if not chunks:
                return "No relevant evidence found in this project for that query."

            enriched = await self._get_chunks_with_neighbors(project_id, chunks)
            enriched = await self._enrich_with_document_details(enriched)
            self._last_evidence_chunks.extend(enriched)
            document_numbers = self._register_evidence_references(enriched)
            return self._build_context(enriched, document_numbers=document_numbers)

        async def _handle_search_parliament(**kwargs: Any) -> str:
            text, items = await search_parliament(**kwargs)
            if not items:
                return text

            self._last_parliament_items.extend(items)
            document_numbers = self._register_parliament_references(items)
            return self._build_parliament_context(items, document_numbers)

        return {
            "search_project_evidence": _handle_search_evidence,
            "search_parliament": _handle_search_parliament,
        }

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

    def _register_evidence_references(
        self, chunks: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Assign stable [Document N] numbers to project evidence documents."""
        document_numbers: Dict[str, int] = {}

        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if not doc_id:
                continue

            doc_number = self._evidence_reference_numbers.get(doc_id)
            if doc_number is None:
                doc_number = len(self._ordered_references) + 1
                self._evidence_reference_numbers[doc_id] = doc_number
                self._ordered_references.append(self._build_document_reference(chunk))

            document_numbers[doc_id] = doc_number

        return document_numbers

    def _register_parliament_references(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Assign stable [Document N] numbers to Hansard search results."""
        document_numbers: Dict[str, int] = {}

        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue

            doc_number = self._parliament_reference_numbers.get(item_id)
            if doc_number is None:
                doc_number = len(self._ordered_references) + 1
                self._parliament_reference_numbers[item_id] = doc_number
                self._ordered_references.append(self._build_parliament_reference(item))

            document_numbers[item_id] = doc_number

        return document_numbers

    def _build_document_reference(self, chunk: Dict[str, Any]) -> DocumentReference:
        """Build a single document reference from an enriched evidence chunk."""
        doi = chunk.get("document_doi")
        overton_url = chunk.get("document_overton_url")
        url = None

        if doi:
            url = f"https://doi.org/{doi}" if not doi.startswith("http") else doi
        elif overton_url:
            url = overton_url

        return DocumentReference(
            document_id=chunk.get("document_id", f"chunk-{id(chunk)}"),
            title=chunk.get("document_title", "Unknown Document"),
            authors=chunk.get("document_authors"),
            doi=doi,
            url=url,
            chunk_type=chunk.get("chunk_type"),
            published_date=chunk.get("document_published_date"),
            year=chunk.get("document_year"),
        )

    def _build_parliament_reference(self, item: Dict[str, Any]) -> DocumentReference:
        """Build a reference entry for a Hansard search result."""
        return DocumentReference(
            document_id=item.get("id", f"hansard-{id(item)}"),
            title=item.get("title", "Parliamentary record"),
            url=item.get("url"),
            published_date=item.get("date"),
        )

    def _build_parliament_references(
        self, items: List[Dict[str, Any]]
    ) -> List[DocumentReference]:
        """Build ordered parliament references without introducing duplicates."""
        references: List[DocumentReference] = []
        seen_ids = set()

        for item in items:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                references.append(self._build_parliament_reference(item))

        return references

    def _build_parliament_context(
        self,
        items: List[Dict[str, Any]],
        document_numbers: Dict[str, int],
    ) -> str:
        """Build Hansard tool context using stable [Document N] numbering."""
        if not items:
            return "No parliamentary results found for this topic."

        parts = []
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue

            doc_number = document_numbers.get(item_id)
            if doc_number is None:
                continue

            part = f"\n--- DOCUMENT {doc_number}: {item['title']} ---\n"
            part += f"Source: UK Parliament Hansard ({item['source_type']})\n"
            part += f"Date: {item['date']}\n"
            part += f"\n[CONTENT]: {item['content']}\n"
            parts.append(part)

        return (
            "\n".join(parts)
            if parts
            else "No parliamentary results found for this topic."
        )


# Global instance
chatbot_service = ChatbotService()
