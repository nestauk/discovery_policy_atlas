"""
Abstract base class for extraction workflows.

Provides shared infrastructure for LangGraph-based document extraction,
including LLM setup, Langfuse integration, retry logic, and validation.
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph

from app.core.config import settings
from app.utils.llm.llm_utils import (
    get_langfuse_handler,
    build_langfuse_metadata,
    resolve_langfuse_session_id,
)
from ..schemas_langchain import (
    DocumentExtractionBundle,
    IssueItem,
    InterventionItem,
    MappingItem,
    ResultItem,
    ConclusionItem,
)

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    """State passed between workflow nodes."""

    paper_id: str
    full_text: str
    evidence_category: str
    evidence_confidence: float
    workflow_type: str  # "rct", "sr", "policy"

    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: Optional[ConclusionItem]

    # SR-specific state
    n_studies_included: Optional[int]
    sr_completeness_flag: Optional[str]

    error: Optional[str]


class BaseExtractionWorkflow(ABC):
    """Abstract base class for extraction workflows.

    Provides shared infrastructure:
    - LLM initialization
    - Langfuse observability integration
    - Retry logic for stage failures
    - Fuzzy quote validation
    - Common metadata building

    Subclasses implement workflow-specific extraction stages and prompts.
    """

    # Subclasses should set this
    workflow_type: str = "base"

    def __init__(
        self,
        model: str = "gpt-5-mini",
        temperature: float = 0.0,
        *,
        policy_project_id: Optional[str] = None,
        policy_user_id: Optional[str] = None,
    ):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for extraction workflows")

        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=settings.OPENAI_API_KEY,
            request_timeout=120.0,
        )
        self.model_name = model
        self.json_parser = JsonOutputParser()
        self.policy_project_id = policy_project_id
        self.policy_user_id = policy_user_id
        self._langfuse_session_id: Optional[str] = None
        self._langfuse_handler = None

        # Build the workflow graph
        self.workflow = self._build_workflow()

    @abstractmethod
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow. Implemented by subclasses."""
        pass

    @abstractmethod
    def _get_workflow_type(self) -> str:
        """Return the workflow type identifier."""
        pass

    async def run(
        self,
        paper_id: str,
        full_text: str,
        evidence_category: str,
        evidence_confidence: float = 1.0,
    ) -> DocumentExtractionBundle:
        """Run the complete extraction workflow."""
        # Create Langfuse session
        session_id = resolve_langfuse_session_id(self.policy_project_id)
        self._langfuse_session_id = session_id
        self._langfuse_handler = get_langfuse_handler(session_id=session_id)

        workflow_type = self._get_workflow_type()

        initial_state = WorkflowState(
            paper_id=paper_id,
            full_text=full_text,
            evidence_category=evidence_category,
            evidence_confidence=evidence_confidence,
            workflow_type=workflow_type,
            issues=[],
            interventions=[],
            mappings=[],
            results=[],
            conclusion=None,
            n_studies_included=None,
            sr_completeness_flag=None,
            error=None,
        )

        try:
            final_state = await self.workflow.ainvoke(initial_state)

            if final_state.get("error"):
                logger.error(f"Workflow error for {paper_id}: {final_state['error']}")
                return self._empty_bundle(paper_id, workflow_type, evidence_category)

            return DocumentExtractionBundle(
                paper_id=paper_id,
                workflow_used=workflow_type,
                routing_reason="evidence_category",
                issues=final_state["issues"],
                interventions=final_state["interventions"],
                mappings=final_state["mappings"],
                results=final_state["results"],
                conclusion=final_state.get("conclusion"),
                n_studies_included=final_state.get("n_studies_included"),
                sr_completeness_flag=final_state.get("sr_completeness_flag"),
            )

        except Exception as e:
            logger.error(f"Workflow failed for {paper_id}: {e}")
            return self._empty_bundle(paper_id, workflow_type, evidence_category)

    def _empty_bundle(
        self, paper_id: str, workflow_type: str, evidence_category: str
    ) -> DocumentExtractionBundle:
        """Return an empty bundle on error."""
        return DocumentExtractionBundle(
            paper_id=paper_id,
            workflow_used=workflow_type,
            routing_reason="evidence_category",
            issues=[],
            interventions=[],
            mappings=[],
            results=[],
            conclusion=None,
        )

    def _build_metadata(
        self, tags: List[str], extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build Langfuse metadata for tracing."""
        return build_langfuse_metadata(
            tags=tags,
            session_id=self._langfuse_session_id,
            user_id=self.policy_user_id,
            project_id=self.policy_project_id,
            extra=extra,
        )

    def _get_callbacks(self) -> List:
        """Get callback handlers for LLM calls."""
        if self._langfuse_handler:
            return [self._langfuse_handler]
        return []

    async def _run_prompt_stage(
        self,
        prompt,
        payload: Dict[str, Any],
        tags: List[str],
        run_name: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a prompt stage with standard callbacks, tags, and metadata."""
        chain = prompt | self.llm | self.json_parser
        return await chain.ainvoke(
            payload,
            config={
                "callbacks": self._get_callbacks(),
                "tags": tags,
                "metadata": self._build_metadata(tags, extra=extra),
                "run_name": run_name,
            },
        )

    async def _extract_with_retry(
        self,
        extract_fn,
        state: WorkflowState,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """Execute an extraction stage with retry logic.

        Args:
            extract_fn: Async function to execute
            state: Current workflow state
            max_retries: Number of retry attempts (default 1)

        Returns:
            Result dict from the extraction, or empty result on failure
        """
        for attempt in range(max_retries + 1):
            try:
                return await extract_fn(state)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"Stage {extract_fn.__name__} failed (attempt {attempt + 1}), retrying: {e}"
                    )
                    await asyncio.sleep(1)  # backoff
                    continue
                logger.error(
                    f"Stage {extract_fn.__name__} failed after {max_retries + 1} attempts: {e}"
                )
                return {}

    def _fuzzy_quote_match(
        self, quote: str, full_text: str, threshold: float = 0.7
    ) -> bool:
        """Check if a quote has substantial overlap with the full text."""
        if not quote or not full_text:
            return False

        # First try exact match (fastest)
        if quote.strip() in full_text:
            return True

        def normalize_text(text: str) -> str:
            text = re.sub(r"\s+", " ", text.strip())
            return text.lower()

        normalized_quote = normalize_text(quote)
        normalized_full_text = normalize_text(full_text)

        # Try normalized exact match
        if normalized_quote in normalized_full_text:
            return True

        # For longer quotes, check word overlap
        if len(normalized_quote) > 50:
            quote_words = set(normalized_quote.split())
            full_text_words = set(normalized_full_text.split())

            common_words = {
                "the",
                "a",
                "an",
                "and",
                "or",
                "but",
                "in",
                "on",
                "at",
                "to",
                "for",
                "of",
                "with",
                "by",
            }
            quote_words -= common_words
            full_text_words -= common_words

            if len(quote_words) == 0:
                return False

            overlap = len(quote_words & full_text_words) / len(quote_words)
            return overlap >= threshold

        # For shorter quotes, check key phrases
        else:
            words = normalized_quote.split()
            if len(words) >= 4:
                phrase = " ".join(words[:4])
                return phrase in normalized_full_text
            else:
                return normalized_quote in normalized_full_text

    def _serialize_for_prompt(self, items: List, key: str) -> str:
        """Serialize a list of Pydantic models to JSON string for prompts."""
        return json.dumps({key: [item.model_dump() for item in items]})

    def _split_by_grounded_quote(
        self, items: List, full_text: str
    ) -> Tuple[List, List]:
        """Split items into valid/invalid based on supporting_quote grounding."""
        valid = []
        invalid = []
        for item in items:
            quote = getattr(item, "supporting_quote", None)
            if quote and self._fuzzy_quote_match(quote, full_text):
                valid.append(item)
            else:
                invalid.append(item)
        return valid, invalid

    def _split_results_by_grounded_quote(
        self,
        results: List[ResultItem],
        valid_intervention_indices: Set[int],
        full_text: str,
    ) -> Tuple[List[ResultItem], List[ResultItem]]:
        """Split results based on grounding and valid intervention indices."""
        valid = []
        invalid = []
        for result in results:
            if (
                result.intervention_idx in valid_intervention_indices
                and result.supporting_quote
                and self._fuzzy_quote_match(result.supporting_quote, full_text)
            ):
                valid.append(result)
            else:
                invalid.append(result)
        return valid, invalid

    def _split_mappings_by_grounded_quote(
        self,
        mappings: List[MappingItem],
        valid_issue_indices: Set[int],
        valid_intervention_indices: Set[int],
        full_text: str,
    ) -> Tuple[List[MappingItem], List[MappingItem]]:
        """Split mappings based on grounding and valid indices."""
        valid = []
        invalid = []
        for mapping in mappings:
            if (
                mapping.issue_idx in valid_issue_indices
                and mapping.intervention_idx in valid_intervention_indices
                and mapping.supporting_quote
                and self._fuzzy_quote_match(mapping.supporting_quote, full_text)
            ):
                valid.append(mapping)
            else:
                invalid.append(mapping)
        return valid, invalid

    def _validate_conclusion(
        self, conclusion: Optional[ConclusionItem], full_text: str
    ) -> Optional[ConclusionItem]:
        """Return the conclusion if it is grounded, else None."""
        if not conclusion or not conclusion.supporting_quote:
            return None
        if self._fuzzy_quote_match(conclusion.supporting_quote, full_text):
            return conclusion
        return None
