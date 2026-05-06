"""
Simple RAG chatbot service for v2 analysis projects.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from openai import AsyncOpenAI
from app.core.config import settings
from app.services.synthesis.logbook import read_cached_summary
from app.services.synthesis.schemas import (
    CitationInfo,
    EvidenceCoverageSnapshot,
    PolicyIntervention,
    SynthesisSummary,
)
from app.services.vectorization import vectorization_service
from .models import (
    ChatEvent,
    ChatRequest,
    ChatResponse,
    ChatStep,
    DocumentReference,
)
from .parliament import search_parliament
from .prompts import (
    EVIDENCE_RETRIEVAL_NOTE,
    PARLIAMENT_RETRIEVAL_NOTE,
    SYNTHESIS_SOURCE_NOTE,
    build_chatbot_system_prompt,
    build_final_answer_retry_prompt,
)

logger = logging.getLogger(__name__)


MAX_AGENT_ITERATIONS = 5
MAX_SYNTHESIS_INTERVENTIONS = 4
MAX_SYNTHESIS_RECOMMENDATIONS = 3
CHATBOT_MAX_COMPLETION_TOKENS = 4000
EMPTY_ASSISTANT_FALLBACK = "I wasn't able to generate a response. Please try again."
CHAT_STREAM_FAILURE_MESSAGE = "Chat request failed. Please try again."
NO_PARLIAMENT_RESULTS_MESSAGE = "No parliamentary results found for this topic."
NO_SYNTHESIS_SUMMARY_MESSAGE = (
    "No synthesised project summary is available for this project yet. "
    "Use search_project_evidence for study-level questions."
)
FINAL_ANSWER_RETRY_PROMPT = build_final_answer_retry_prompt()
SYNTHESIS_CITATION_GROUP_RE = re.compile(r"\[((?:\d+\s*,\s*)*\d+)\]")
DOCUMENT_CITATION_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
REFERENCE_SECTION_RE = re.compile(
    r"\n(?:Sources cited|Sources|References|Cited documents)\s*:?\s*\n.*\Z",
    re.IGNORECASE | re.DOTALL,
)
INTERNAL_TOOL_CITATION_RE = re.compile(
    r"\[(?:get_project_synthesis|search_project_evidence|search_parliament)[^\]]*\]",
    re.IGNORECASE,
)
INTERNAL_SYNTHESIS_LABEL_RE = re.compile(
    r"\[(?:[^\]]*(?:synthesis|top interventions?|overview|section)[^\]]*)\]",
    re.IGNORECASE,
)
BOTTOM_LINE_PREFIX_RE = re.compile(r"^\s*Bottom line:\s*", re.IGNORECASE)
POLICY_HEADING_RE = re.compile(
    r"\n(?:What this means for policy|Policy implication(?:s)?|Practical policy implications)\s*:\s*\n",
    re.IGNORECASE,
)
TOOL_LABELS = {
    "get_project_synthesis": "Checking project synthesis",
    "search_project_evidence": "Searching project evidence",
    "search_parliament": "Looking up Parliament records",
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_project_synthesis",
        "description": "Fetch the project's synthesised evidence summary for high-level questions about what works, main findings, top interventions, or recommendations.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "strict": False,
    },
    {
        "type": "function",
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
        "strict": False,
    },
    {
        "type": "function",
        "name": "search_parliament",
        "description": "Search UK Parliament records including Hansard debates, contributions, written statements, written answers, and answered written parliamentary questions. Use short specific keyword queries rather than full sentences.",
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
        "strict": False,
    },
]


@dataclass
class ToolExecutionResult:
    """Normalized tool output plus bounded UI metadata."""

    content: str
    summary: Optional[str] = None


@dataclass
class ChatTurnState:
    """Request-scoped mutable state for one chat turn."""

    last_evidence_chunks: List[Dict[str, Any]]
    last_parliament_items: List[Dict[str, Any]]
    ordered_references: List[DocumentReference]
    evidence_reference_numbers: Dict[str, int]
    parliament_reference_numbers: Dict[str, int]

    @classmethod
    def create(cls) -> "ChatTurnState":
        """Create empty turn state for a fresh chat request."""
        return cls(
            last_evidence_chunks=[],
            last_parliament_items=[],
            ordered_references=[],
            evidence_reference_numbers={},
            parliament_reference_numbers={},
        )


EventEmitter = Callable[[ChatEvent], Awaitable[None]]


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
        """Generate a chat response using tool-calling agent loop."""
        return await self._execute_chat_turn(project_id, request)

    async def stream_chat_events(
        self, project_id: str, request: ChatRequest
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream structured step events for a single chat turn."""
        queue: asyncio.Queue[Optional[ChatEvent]] = asyncio.Queue()

        async def _emit(event: ChatEvent) -> None:
            await queue.put(event)

        async def _run() -> None:
            try:
                response = await self._execute_chat_turn(
                    project_id,
                    request,
                    emit_event=_emit,
                )
                await _emit(
                    ChatEvent(
                        type="message.completed",
                        message=response.message,
                        references=response.references,
                        activity_summary=response.activity_summary,
                    )
                )
            except Exception:
                logger.exception("Error streaming chat for project %s", project_id)
                await _emit(
                    ChatEvent(
                        type="message.failed",
                        error=CHAT_STREAM_FAILURE_MESSAGE,
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event.model_dump(mode="json", exclude_none=True)
        finally:
            await task

    async def _execute_chat_turn(
        self,
        project_id: str,
        request: ChatRequest,
        emit_event: Optional[EventEmitter] = None,
    ) -> ChatResponse:
        """Run one chat turn and optionally emit step events while it executes."""
        turn_state = ChatTurnState.create()
        tool_handlers = self._build_tool_handlers(project_id, turn_state)
        steps: List[ChatStep] = []

        project_title = await self._get_project_title(project_id)
        instructions = self._build_system_prompt(project_title)

        input_items: List[Any] = []
        if request.recent_messages:
            for msg in request.recent_messages[-5:]:
                input_items.append({"role": msg.role.value, "content": msg.content})
        input_items.append({"role": "user", "content": request.message})

        final_message = await self._run_agent_loop(
            input_items,
            tool_handlers,
            instructions=instructions,
            steps=steps,
            emit_event=emit_event,
        )
        final_content = self._extract_assistant_text(final_message)
        has_final_content = bool(final_content)
        if not has_final_content:
            final_content = EMPTY_ASSISTANT_FALLBACK
        else:
            final_content = self._sanitize_final_message(final_content)

        references: List[DocumentReference] = []
        if has_final_content:
            references = self._get_ordered_references(turn_state)
            if not references:
                references = self._build_references(turn_state.last_evidence_chunks)
                references.extend(
                    self._build_parliament_references(turn_state.last_parliament_items)
                )
            final_content, references = self._compact_cited_references(
                final_content,
                references,
            )
            final_content = self._strip_unresolved_internal_citations(final_content)

        activity_summary = self._build_activity_summary(steps, references)

        return ChatResponse(
            message=final_content,
            references=references,
            steps=steps,
            activity_summary=activity_summary,
        )

    def _get_ordered_references(
        self, turn_state: ChatTurnState
    ) -> List[DocumentReference]:
        """Return references in the same order used for [Document N] citations."""
        return list(turn_state.ordered_references)

    def _build_activity_summary(
        self,
        steps: List[ChatStep],
        references: List[DocumentReference],
    ) -> str:
        """Build the compact post-hoc summary shown above the final answer."""
        action_count = sum(1 for step in steps if step.type == "tool")
        source_count = len(references)
        return (
            f"Used {action_count} action{'s' if action_count != 1 else ''} "
            f"and {source_count} source{'s' if source_count != 1 else ''}"
        )

    def _truncate_for_label(self, value: str, max_chars: int = 60) -> str:
        """Shorten a query so status labels stay readable inside the chat UI."""
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[: max_chars - 3].rstrip()}..."

    def _build_tool_step_label(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Map internal tools to user-facing labels with bounded context."""
        arguments = arguments or {}
        query = arguments.get("query")
        if isinstance(query, str) and query.strip():
            truncated_query = self._truncate_for_label(query)
            if tool_name == "search_project_evidence":
                return f'Searching project evidence for "{truncated_query}"'
            if tool_name == "search_parliament":
                return f'Looking up Parliament records for "{truncated_query}"'

        return TOOL_LABELS.get(tool_name, "Working")

    def _build_synthesis_summary(self, content: str) -> str:
        """Summarize synthesis retrieval without exposing raw synthesis text."""
        normalized = content.strip()
        if normalized == NO_SYNTHESIS_SUMMARY_MESSAGE:
            return "No synthesis summary available"
        if normalized.startswith("Project synthesis could not be loaded"):
            return "Synthesis could not be loaded"
        return "Synthesis found"

    def _format_count_summary(self, count: int, singular: str, plural: str) -> str:
        """Render a short, human-readable count summary."""
        noun = singular if count == 1 else plural
        return f"{count} relevant {noun} found"

    def _next_step_id(self, steps: List[ChatStep]) -> str:
        """Generate a stable per-turn step identifier."""
        return f"step-{len(steps) + 1}"

    async def _emit_event(
        self,
        emit_event: Optional[EventEmitter],
        event_type: str,
        *,
        step: Optional[ChatStep] = None,
        message: Optional[str] = None,
        references: Optional[List[DocumentReference]] = None,
        activity_summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Emit a structured chat event when a subscriber is attached."""
        if emit_event is None:
            return

        await emit_event(
            ChatEvent(
                type=event_type,
                step=step.model_copy(deep=True) if step is not None else None,
                message=message,
                references=references or [],
                activity_summary=activity_summary,
                error=error,
            )
        )

    async def _start_status_step(
        self,
        steps: List[ChatStep],
        label: str,
        emit_event: Optional[EventEmitter],
    ) -> ChatStep:
        """Start a visible non-tool status step."""
        step = ChatStep(
            id=self._next_step_id(steps),
            type="status",
            label=label,
            status="running",
        )
        steps.append(step)
        await self._emit_event(emit_event, "agent.status", step=step)
        return step

    async def _start_tool_step(
        self,
        steps: List[ChatStep],
        tool_name: str,
        arguments: Dict[str, Any],
        emit_event: Optional[EventEmitter],
    ) -> ChatStep:
        """Start a visible tool execution step."""
        step = ChatStep(
            id=self._next_step_id(steps),
            type="tool",
            label=self._build_tool_step_label(tool_name, arguments),
            status="running",
        )
        steps.append(step)
        await self._emit_event(emit_event, "tool.started", step=step)
        return step

    async def _complete_step(
        self,
        step: Optional[ChatStep],
        emit_event: Optional[EventEmitter],
        *,
        event_type: str = "agent.status",
        summary: Optional[str] = None,
    ) -> None:
        """Mark a step completed and emit the updated snapshot."""
        if step is None or step.status in {"completed", "failed"}:
            return
        step.status = "completed"
        if summary:
            step.summary = summary
        await self._emit_event(emit_event, event_type, step=step)

    async def _fail_step(
        self,
        step: Optional[ChatStep],
        emit_event: Optional[EventEmitter],
        *,
        summary: Optional[str] = None,
    ) -> None:
        """Mark a step failed and emit the updated snapshot."""
        if step is None or step.status in {"completed", "failed"}:
            return
        step.status = "failed"
        if summary:
            step.summary = summary
        await self._emit_event(emit_event, "tool.failed", step=step)

    async def _ensure_drafting_step(
        self,
        steps: List[ChatStep],
        active_status_step: Optional[ChatStep],
        emit_event: Optional[EventEmitter],
    ) -> ChatStep:
        """Ensure the current non-tool step reflects answer drafting."""
        if (
            active_status_step is not None
            and active_status_step.status == "running"
            and active_status_step.label == "Drafting answer"
        ):
            return active_status_step

        if active_status_step is not None and active_status_step.status == "running":
            await self._complete_step(active_status_step, emit_event)

        return await self._start_status_step(steps, "Drafting answer", emit_event)

    def _parse_tool_arguments(self, raw_arguments: Any) -> Dict[str, Any]:
        """Parse tool-call arguments into a dictionary."""
        if raw_arguments in (None, ""):
            return {}
        if isinstance(raw_arguments, dict):
            return raw_arguments

        parsed = json.loads(raw_arguments)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return parsed

    def _build_system_prompt(self, project_title: Optional[str] = None) -> str:
        """Build system prompt for the tool-calling agent."""
        return build_chatbot_system_prompt(project_title)

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

    async def _get_project_synthesis(
        self,
        project_id: str,
        turn_state: Optional[ChatTurnState] = None,
    ) -> str:
        """Fetch and format cached synthesis output for chat use."""
        try:
            summary = await read_cached_summary(project_id)
        except Exception as exc:
            logger.warning(
                "Failed to read synthesis summary for project %s: %s",
                project_id,
                exc,
            )
            return (
                "Project synthesis could not be loaded for this project. "
                "Use search_project_evidence for study-level evidence instead."
            )

        if summary is None:
            return self._format_project_synthesis(summary)

        effective_turn_state = turn_state or ChatTurnState.create()
        citation_mapping = self._register_synthesis_references(
            effective_turn_state,
            summary.citation_map,
        )
        formatted = self._format_project_synthesis(summary)
        return self._remap_synthesis_citations(formatted, citation_mapping)

    def _format_project_synthesis(self, summary: Optional[SynthesisSummary]) -> str:
        """Render cached synthesis output into a compact tool response."""
        if summary is None:
            return NO_SYNTHESIS_SUMMARY_MESSAGE

        parts: List[str] = [SYNTHESIS_SOURCE_NOTE]
        briefing = summary.structured_briefing

        if briefing is not None:
            headline_parts = ["HEADLINE", briefing.core_answer.answer.strip()]
            directive = briefing.core_answer.directive.strip()
            if directive:
                headline_parts.append(f"Directive: {directive}")
            parts.append("\n".join(headline_parts))

            interventions_section = self._format_briefing_interventions(
                briefing.interventions_table
            )
            if interventions_section:
                parts.append(interventions_section)
            elif summary.interventions:
                parts.append(
                    self._format_aggregated_interventions(summary.interventions)
                )

            evidence_snapshot = briefing.evidence_snapshot_summary.strip()
            if evidence_snapshot:
                parts.append(f"EVIDENCE SNAPSHOT\n{evidence_snapshot}")
            else:
                coverage_section = self._format_evidence_coverage(
                    summary.evidence_coverage
                )
                if coverage_section:
                    parts.append(coverage_section)

            recommendations_section = self._format_recommendations(
                briefing.recommendations
            )
            if recommendations_section:
                parts.append(recommendations_section)
        else:
            parts.append(
                "No structured briefing is available, but the cached synthesis includes aggregated intervention summaries."
            )
            if summary.interventions:
                parts.append(
                    self._format_aggregated_interventions(summary.interventions)
                )

            coverage_section = self._format_evidence_coverage(summary.evidence_coverage)
            if coverage_section:
                parts.append(coverage_section)

        if not parts or (
            len(parts) == 1
            and parts[0].startswith("No structured briefing is available")
            and not summary.interventions
            and summary.evidence_coverage is None
        ):
            return NO_SYNTHESIS_SUMMARY_MESSAGE

        return "\n\n".join(parts)

    def _format_briefing_interventions(self, interventions: List[Any]) -> str:
        """Format structured briefing intervention rows in their existing order."""
        if not interventions:
            return ""

        lines = ["TOP INTERVENTIONS"]
        displayed = interventions[:MAX_SYNTHESIS_INTERVENTIONS]
        for row in displayed:
            detail_parts = []
            impact_narrative = getattr(row, "impact_narrative", "").strip()
            context = getattr(row, "context", "").strip()
            key_study = getattr(row, "key_study_description", "").strip()

            if impact_narrative:
                detail_parts.append(impact_narrative)
            if context:
                detail_parts.append(f"Context: {context}")
            if key_study:
                detail_parts.append(f"Key study: {key_study}")

            line = f"- {row.intervention_name}"
            if detail_parts:
                line += f": {' '.join(detail_parts)}"
            lines.append(line)

        remaining = len(interventions) - len(displayed)
        if remaining > 0:
            lines.append(
                f"More interventions are available in the cached synthesis ({remaining} more)."
            )

        return "\n".join(lines)

    def _format_aggregated_interventions(
        self, interventions: List[PolicyIntervention]
    ) -> str:
        """Fallback formatter when no structured briefing is present."""
        if not interventions:
            return ""

        lines = ["TOP INTERVENTIONS"]
        displayed = interventions[:MAX_SYNTHESIS_INTERVENTIONS]
        for intervention in displayed:
            summary = (
                intervention.impact_summary.strip()
                or intervention.brief_description.strip()
            )
            line = f"- {intervention.intervention_name}"
            if summary:
                line += f": {summary}"
            lines.append(line)

        remaining = len(interventions) - len(displayed)
        if remaining > 0:
            lines.append(
                f"More aggregated interventions are available in the cached synthesis ({remaining} more)."
            )

        return "\n".join(lines)

    def _format_evidence_coverage(
        self, coverage: Optional[EvidenceCoverageSnapshot]
    ) -> str:
        """Summarize deterministic evidence coverage stats."""
        if coverage is None:
            return ""

        sentences = [
            f"Synthesised {coverage.total_synthesised} evidence documents from {coverage.total_screened} screened."
        ]

        if coverage.overall_strength and coverage.overall_strength != "Unknown":
            sentences.append(f"Overall strength: {coverage.overall_strength}.")

        if coverage.study_types:
            top_study_types = ", ".join(
                f"{study_type} ({count})"
                for study_type, count in list(coverage.study_types.items())[:3]
            )
            sentences.append(f"Study types: {top_study_types}.")

        if coverage.gaps:
            sentences.append(f"Evidence gaps: {coverage.gaps[0]}.")

        return f"EVIDENCE SNAPSHOT\n{' '.join(sentences)}"

    def _format_recommendations(self, recommendations: List[Any]) -> str:
        """Format a small number of structured recommendations."""
        if not recommendations:
            return ""

        lines = ["RECOMMENDATIONS"]
        displayed = recommendations[:MAX_SYNTHESIS_RECOMMENDATIONS]
        for recommendation in displayed:
            line = f"{recommendation.number}. {recommendation.title}"
            description = recommendation.description.strip()
            if description:
                line += f": {description}"
            lines.append(line)

        remaining = len(recommendations) - len(displayed)
        if remaining > 0:
            lines.append(
                f"More recommendations are available in the cached synthesis ({remaining} more)."
            )

        return "\n".join(lines)

    def _register_synthesis_references(
        self, turn_state: ChatTurnState, citation_map: Dict[str, CitationInfo]
    ) -> Dict[int, int]:
        """Assign chatbot [Document N] numbers to synthesis citations."""
        citation_number_mapping: Dict[int, int] = {}

        ordered_citations = sorted(
            (
                citation
                for citation in citation_map.values()
                if citation.citation_number and citation.citation_number > 0
            ),
            key=lambda citation: citation.citation_number,
        )

        for citation in ordered_citations:
            reference_key = self._get_synthesis_reference_key(citation)
            doc_number = turn_state.evidence_reference_numbers.get(reference_key)

            if doc_number is None:
                doc_number = len(turn_state.ordered_references) + 1
                turn_state.evidence_reference_numbers[reference_key] = doc_number
                turn_state.ordered_references.append(
                    self._build_synthesis_reference(citation, reference_key)
                )

            citation_number_mapping[citation.citation_number] = doc_number

        return citation_number_mapping

    def _get_synthesis_reference_key(self, citation: CitationInfo) -> str:
        """Build a stable internal key for synthesis citation reuse."""
        if citation.analysis_document_id:
            return citation.analysis_document_id
        if citation.doc_id:
            return citation.doc_id
        if citation.citation_key:
            return citation.citation_key
        return f"synthesis-{citation.citation_number}"

    def _build_synthesis_reference(
        self, citation: CitationInfo, reference_key: str
    ) -> DocumentReference:
        """Build a chatbot reference entry from synthesis citation metadata."""
        authors = citation.authors
        if not authors and citation.author_display:
            authors = [citation.author_display]

        return DocumentReference(
            document_id=reference_key,
            title=citation.title or f"Synthesis citation {citation.citation_number}",
            authors=authors,
            url=citation.url,
            year=citation.year,
        )

    def _remap_synthesis_citations(
        self, text: str, citation_number_mapping: Dict[int, int]
    ) -> str:
        """Convert cached synthesis [N] citations into compact chatbot citations."""
        if not text or not citation_number_mapping:
            return text

        def _replace(match: re.Match[str]) -> str:
            numbers = []
            for raw_part in match.group(1).split(","):
                raw_part = raw_part.strip()
                if not raw_part.isdigit():
                    return match.group(0)
                numbers.append(int(raw_part))

            remapped_parts: List[str] = []
            for number in numbers:
                mapped = citation_number_mapping.get(number)
                if mapped is None:
                    remapped_parts.append(f"[{number}]")
                else:
                    remapped_parts.append(f"[{mapped}]")

            return "".join(remapped_parts)

        return SYNTHESIS_CITATION_GROUP_RE.sub(_replace, text)

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

        context_parts = [EVIDENCE_RETRIEVAL_NOTE]

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
            doc_context = f"\n--- SOURCE [{doc_number}]: {doc_info['title']} ---\n"

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
        input_items: List[Any],
        tool_handlers: Dict[str, Callable],
        *,
        instructions: Optional[str] = None,
        steps: Optional[List[ChatStep]] = None,
        emit_event: Optional[EventEmitter] = None,
    ) -> Any:
        """Run the tool-calling agent loop via the Responses API."""
        step_list = steps if steps is not None else []
        active_status_step = await self._start_status_step(
            step_list,
            "Understanding your question",
            emit_event,
        )

        for iteration in range(MAX_AGENT_ITERATIONS):
            logger.info("[chatbot] Agent loop iteration %d", iteration + 1)
            response = await self._create_response(
                input_items, instructions=instructions
            )
            function_calls = [
                item for item in response.output if item.type == "function_call"
            ]

            if not function_calls:
                assistant_text = response.output_text
                if not assistant_text:
                    logger.warning(
                        "[chatbot] Empty final response after iteration %d; retrying without tools",
                        iteration + 1,
                    )
                    return await self._request_final_answer(
                        input_items,
                        instructions=instructions,
                        steps=step_list,
                        emit_event=emit_event,
                        active_status_step=active_status_step,
                    )

                await self._complete_step(active_status_step, emit_event)
                logger.info(
                    "[chatbot] Final response (%d chars): %s",
                    len(assistant_text),
                    assistant_text[:200],
                )
                return SimpleNamespace(content=assistant_text, tool_calls=None)

            await self._complete_step(active_status_step, emit_event)

            input_items.extend(response.output)

            for fc in function_calls:
                tool_name = fc.name
                handler = tool_handlers.get(tool_name)

                try:
                    kwargs = self._parse_tool_arguments(fc.arguments)
                except Exception as exc:
                    logger.warning(
                        "[chatbot] Failed to parse tool arguments for %s: %s",
                        tool_name,
                        exc,
                    )
                    kwargs = {}
                    step = await self._start_tool_step(
                        step_list,
                        tool_name,
                        kwargs,
                        emit_event,
                    )
                    failure_reason = f"Invalid tool arguments: {exc}"
                    await self._fail_step(
                        step,
                        emit_event,
                        summary="Tool failed",
                    )
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": fc.call_id,
                            "output": failure_reason,
                        }
                    )
                    continue

                logger.info(
                    "[chatbot] Tool call: %s(%s)",
                    tool_name,
                    fc.arguments,
                )
                step = await self._start_tool_step(
                    step_list,
                    tool_name,
                    kwargs,
                    emit_event,
                )

                if handler is None:
                    tool_result = ToolExecutionResult(
                        content=f"Error: Unknown tool '{tool_name}'",
                        summary="Tool unavailable",
                    )
                    await self._fail_step(
                        step,
                        emit_event,
                        summary=tool_result.summary,
                    )
                else:
                    try:
                        raw_tool_result = await handler(**kwargs)
                        if isinstance(raw_tool_result, ToolExecutionResult):
                            tool_result = raw_tool_result
                        else:
                            tool_result = ToolExecutionResult(
                                content=str(raw_tool_result)
                            )
                        await self._complete_step(
                            step,
                            emit_event,
                            event_type="tool.completed",
                            summary=tool_result.summary,
                        )
                    except Exception as exc:
                        logger.warning("Tool %s failed: %s", tool_name, exc)
                        tool_result = ToolExecutionResult(
                            content=f"Error executing {tool_name}: {exc}",
                            summary="Tool failed",
                        )
                        await self._fail_step(
                            step,
                            emit_event,
                            summary=tool_result.summary,
                        )

                logger.info(
                    "[chatbot] Tool result (%d chars): %s",
                    len(tool_result.content),
                    tool_result.content[:300],
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": tool_result.content,
                    }
                )

            active_status_step = await self._ensure_drafting_step(
                step_list,
                None,
                emit_event,
            )

        logger.warning("[chatbot] Hit agent iteration cap; forcing final answer")
        return await self._request_final_answer(
            input_items,
            instructions=instructions,
            steps=step_list,
            emit_event=emit_event,
            active_status_step=active_status_step,
        )

    async def _create_response(
        self,
        input_items: List[Any],
        *,
        instructions: Optional[str] = None,
        tool_choice: Optional[str] = None,
    ) -> Any:
        """Create a response using the Responses API with the configured chatbot model."""
        request_kwargs: Dict[str, Any] = {
            "model": settings.CHATBOT_MODEL,
            "input": input_items,
            "tools": TOOL_DEFINITIONS,
            "max_output_tokens": CHATBOT_MAX_COMPLETION_TOKENS,
        }

        if instructions is not None:
            request_kwargs["instructions"] = instructions

        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice

        model_name = settings.CHATBOT_MODEL
        if model_name.startswith("gpt-5"):
            request_kwargs["reasoning"] = {
                "effort": settings.CHATBOT_REASONING_EFFORT,
            }
        else:
            request_kwargs["temperature"] = settings.LLM_TEMPERATURE

        return await self.openai_client.responses.create(**request_kwargs)

    async def _request_final_answer(
        self,
        input_items: List[Any],
        *,
        instructions: Optional[str] = None,
        steps: Optional[List[ChatStep]] = None,
        emit_event: Optional[EventEmitter] = None,
        active_status_step: Optional[ChatStep] = None,
    ) -> Any:
        """Force a plain-text answer using already retrieved tool outputs."""
        step_list = steps if steps is not None else []
        if step_list is not None:
            active_status_step = await self._ensure_drafting_step(
                step_list,
                active_status_step,
                emit_event,
            )

        retry_input = input_items + [
            {"role": "user", "content": FINAL_ANSWER_RETRY_PROMPT}
        ]
        response = await self._create_response(
            retry_input,
            instructions=instructions,
            tool_choice="none",
        )
        assistant_text = response.output_text
        await self._complete_step(
            active_status_step,
            emit_event,
            summary="Answer drafted" if assistant_text else None,
        )
        return SimpleNamespace(content=assistant_text, tool_calls=None)

    def _extract_assistant_text(self, message: Any) -> str:
        """Normalize assistant content into a plain text string."""
        return self._extract_text_content(getattr(message, "content", None))

    def _extract_text_content(self, content: Any) -> str:
        """Normalize OpenAI content payloads into plain text."""
        if isinstance(content, str):
            return content.strip()

        if not isinstance(content, list):
            return ""

        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = getattr(item, "text", None)

            if isinstance(text, str) and text.strip():
                parts.append(text.strip())

        return "\n".join(parts).strip()

    def _build_tool_handlers(
        self,
        project_id: str,
        turn_state: Optional[ChatTurnState] = None,
    ) -> Dict[str, Callable]:
        """Build tool handler dict for the agent loop."""
        effective_turn_state = turn_state or ChatTurnState.create()

        async def _handle_get_project_synthesis(**_: Any) -> ToolExecutionResult:
            content = await self._get_project_synthesis(
                project_id, effective_turn_state
            )
            return ToolExecutionResult(
                content=content,
                summary=self._build_synthesis_summary(content),
            )

        async def _handle_search_evidence(query: str) -> ToolExecutionResult:
            chunks = await self._search_relevant_chunks(project_id, query)
            if not chunks:
                return ToolExecutionResult(
                    content="No relevant evidence found in this project for that query.",
                    summary="No relevant documents found",
                )

            enriched = await self._get_chunks_with_neighbors(project_id, chunks)
            enriched = await self._enrich_with_document_details(enriched)
            effective_turn_state.last_evidence_chunks.extend(enriched)
            document_numbers = self._register_evidence_references(
                effective_turn_state,
                enriched,
            )
            document_count = len(
                {
                    chunk.get("document_id")
                    for chunk in enriched
                    if chunk.get("document_id")
                }
            )
            return ToolExecutionResult(
                content=self._build_context(
                    enriched,
                    document_numbers=document_numbers,
                ),
                summary=self._format_count_summary(
                    document_count,
                    "document",
                    "documents",
                ),
            )

        async def _handle_search_parliament(**kwargs: Any) -> ToolExecutionResult:
            text, items = await search_parliament(**kwargs)
            if not items:
                return ToolExecutionResult(
                    content=text,
                    summary="No Parliament records found",
                )

            effective_turn_state.last_parliament_items.extend(items)
            document_numbers = self._register_parliament_references(
                effective_turn_state,
                items,
            )
            return ToolExecutionResult(
                content=self._build_parliament_context(items, document_numbers),
                summary=self._format_count_summary(
                    len(items),
                    "record",
                    "records",
                ),
            )

        return {
            "get_project_synthesis": _handle_get_project_synthesis,
            "search_project_evidence": _handle_search_evidence,
            "search_parliament": _handle_search_parliament,
        }

    def _build_document_url(
        self,
        doi: Optional[str],
        overton_url: Optional[str],
    ) -> Optional[str]:
        """Build a reference URL from DOI metadata or an existing document URL."""
        if doi:
            return f"https://doi.org/{doi}" if not doi.startswith("http") else doi
        return overton_url

    def _build_references(
        self, chunks: List[Dict[str, Any]]
    ) -> List[DocumentReference]:
        """Build document references from chunks."""
        references: List[DocumentReference] = []
        seen_docs = set()

        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)
                references.append(self._build_document_reference(chunk))

        return references

    def _parse_document_citation_group(self, bracket_content: str) -> List[int]:
        """Parse a citation group like '5', 'Document 5', or 'Documents 5 and 7'."""
        document_match = re.search(
            r"\bdocuments?\b(?P<tail>.+)$",
            bracket_content,
            flags=re.IGNORECASE,
        )
        cleaned = (
            document_match.group("tail")
            if document_match is not None
            else re.sub(r"\bdocuments?\b", "", bracket_content, flags=re.IGNORECASE)
        )
        cleaned = cleaned.replace("&", ",")
        cleaned = re.sub(r"\band\b", ",", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")

        if not cleaned or not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", cleaned):
            return []

        return [int(part.strip()) for part in cleaned.split(",")]

    def _extract_cited_document_numbers(self, text: str) -> List[int]:
        """Return cited document numbers in first-appearance order."""
        if not text:
            return []

        seen_numbers = set()
        ordered_numbers: List[int] = []
        for match in DOCUMENT_CITATION_BRACKET_RE.finditer(text):
            for number in self._parse_document_citation_group(match.group(1)):
                if number in seen_numbers:
                    continue
                seen_numbers.add(number)
                ordered_numbers.append(number)
        return ordered_numbers

    def _compact_cited_references(
        self,
        message: str,
        references: List[DocumentReference],
    ) -> tuple[str, List[DocumentReference]]:
        """Renumber cited references compactly and return only those references."""
        cited_numbers = self._extract_cited_document_numbers(message)
        if not cited_numbers:
            return message, []

        number_mapping: Dict[int, int] = {}
        filtered: List[DocumentReference] = []
        for number in cited_numbers:
            index = number - 1
            if 0 <= index < len(references):
                number_mapping[number] = len(filtered) + 1
                filtered.append(references[index])

        if not filtered:
            return message, references

        def _replace(match: re.Match[str]) -> str:
            original_numbers = self._parse_document_citation_group(match.group(1))
            if not original_numbers:
                return match.group(0)

            remapped_parts = [
                f"[{number_mapping[number]}]"
                for number in original_numbers
                if number in number_mapping
            ]
            return "".join(remapped_parts) or match.group(0)

        return DOCUMENT_CITATION_BRACKET_RE.sub(_replace, message), filtered

    def _register_evidence_references(
        self,
        turn_state: ChatTurnState,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Assign stable [Document N] numbers to project evidence documents."""
        document_numbers: Dict[str, int] = {}

        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if not doc_id:
                continue

            doc_number = turn_state.evidence_reference_numbers.get(doc_id)
            if doc_number is None:
                doc_number = len(turn_state.ordered_references) + 1
                turn_state.evidence_reference_numbers[doc_id] = doc_number
                turn_state.ordered_references.append(
                    self._build_document_reference(chunk)
                )

            document_numbers[doc_id] = doc_number

        return document_numbers

    def _register_parliament_references(
        self,
        turn_state: ChatTurnState,
        items: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Assign stable [Document N] numbers to Parliament search results."""
        document_numbers: Dict[str, int] = {}

        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue

            doc_number = turn_state.parliament_reference_numbers.get(item_id)
            if doc_number is None:
                doc_number = len(turn_state.ordered_references) + 1
                turn_state.parliament_reference_numbers[item_id] = doc_number
                turn_state.ordered_references.append(
                    self._build_parliament_reference(item)
                )

            document_numbers[item_id] = doc_number

        return document_numbers

    def _build_document_reference(self, chunk: Dict[str, Any]) -> DocumentReference:
        """Build a single document reference from an enriched evidence chunk."""
        doi = chunk.get("document_doi")
        overton_url = chunk.get("document_overton_url")
        url = self._build_document_url(doi, overton_url)

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
        """Build a reference entry for a Parliament search result."""
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
        """Build Parliament tool context using stable [Document N] numbering."""
        if not items:
            return NO_PARLIAMENT_RESULTS_MESSAGE

        parts = [PARLIAMENT_RETRIEVAL_NOTE]
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue

            doc_number = document_numbers.get(item_id)
            if doc_number is None:
                continue

            part = f"\n--- SOURCE [{doc_number}]: {item['title']} ---\n"
            part += (
                f"Source: {item.get('source_display', 'UK Parliament')} "
                f"({item['source_type']})\n"
            )
            part += f"Date: {item['date']}\n"
            part += f"\n[CONTENT]: {item['content']}\n"
            parts.append(part)

        return "\n".join(parts) if parts else NO_PARLIAMENT_RESULTS_MESSAGE

    def _sanitize_final_message(self, message: str) -> str:
        """Remove duplicated reference sections before citation compaction."""
        sanitized = REFERENCE_SECTION_RE.sub("", message).strip()
        sanitized = BOTTOM_LINE_PREFIX_RE.sub("", sanitized)
        sanitized = POLICY_HEADING_RE.sub("\n", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    def _strip_unresolved_internal_citations(self, message: str) -> str:
        """Drop any leftover internal citation markers after citation compaction."""
        cleaned = INTERNAL_TOOL_CITATION_RE.sub("", message)
        cleaned = INTERNAL_SYNTHESIS_LABEL_RE.sub("", cleaned)
        cleaned = re.sub(r" \.", ".", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


# Global instance
chatbot_service = ChatbotService()
