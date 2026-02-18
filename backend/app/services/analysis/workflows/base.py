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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.core.config import settings
from app.utils.llm.llm_utils import (
    get_langfuse_handler,
    build_langfuse_metadata,
    resolve_langfuse_session_id,
)
from ..prompts import CONCLUSIONS_PROMPT
from ..schemas_langchain import (
    DocumentExtractionBundle,
    IssueItem,
    InterventionItem,
    MappingItem,
    ResultItem,
    ConclusionItem,
)
from ..evidence.category import EVIDENCE_CATEGORY_EXPLANATIONS
from ..evidence.strength import calculate_document_evidence_score

logger = logging.getLogger(__name__)


@dataclass
class StageModelConfig:
    """Per-stage model configuration for extraction workflows."""

    issues: Optional[str] = "gpt-4o-mini"
    interventions: Optional[str] = "gpt-4o-mini"
    mappings: Optional[str] = "gpt-4o-mini"
    results: Optional[str] = "gpt-4o-mini"
    conclusions: Optional[str] = "gpt-5-mini"


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

    # Subclasses must set this to identify the workflow type
    workflow_type: str = "base"

    def __init__(
        self,
        model: str = "gpt-5-mini",
        stage_models: Optional[StageModelConfig] = None,
        temperature: float = 0.0,
        *,
        policy_project_id: Optional[str] = None,
        policy_user_id: Optional[str] = None,
    ):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for extraction workflows")

        self.model_name = model
        self.stage_models = stage_models
        self._llms: Dict[str, ChatOpenAI] = {}
        for stage in ["issues", "interventions", "mappings", "results", "conclusions"]:
            stage_model = self._model_for_stage(stage)
            self._llms[stage] = ChatOpenAI(
                model=stage_model,
                temperature=temperature,
                openai_api_key=settings.OPENAI_API_KEY,
                request_timeout=120.0,
            )
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=settings.OPENAI_API_KEY,
            request_timeout=120.0,
        )
        self.json_parser = JsonOutputParser()
        self.policy_project_id = policy_project_id
        self.policy_user_id = policy_user_id
        self._langfuse_session_id: Optional[str] = None
        self._langfuse_handler = None

        # Build the workflow graph
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the standard extraction workflow graph.

        All workflows follow the same structure:
        Issues -> Interventions -> Mappings -> Results -> Conclusions -> Validation

        Subclasses implement the stage methods to customize prompts and processing.
        """
        workflow = StateGraph(WorkflowState)

        workflow.add_node("extract_issues", self._extract_issues)
        workflow.add_node("extract_interventions", self._extract_interventions)
        workflow.add_node("extract_mappings", self._extract_mappings)
        workflow.add_node("extract_results", self._extract_results)
        workflow.add_node("extract_conclusions", self._extract_conclusions)
        workflow.add_node("validate_and_filter", self._validate_and_filter)

        workflow.set_entry_point("extract_issues")
        workflow.add_edge("extract_issues", "extract_interventions")
        workflow.add_edge("extract_interventions", "extract_mappings")
        workflow.add_edge("extract_mappings", "extract_results")
        workflow.add_edge("extract_results", "extract_conclusions")
        workflow.add_edge("extract_conclusions", "validate_and_filter")
        workflow.add_edge("validate_and_filter", END)

        return workflow.compile()

    def _build_evidence_strength_context(self, state: WorkflowState) -> str:
        """Build a compact evidence-strength context string for prompts."""
        category = (
            state.get("evidence_category") or "Unknown / Insufficient information"
        )
        confidence = state.get("evidence_confidence")

        interventions = state.get("interventions") or []
        extraction_results = {
            "interventions": [
                intervention.model_dump() for intervention in interventions
            ]
        }
        doc_stub = {
            "evidence_category": category,
            "extraction_results": extraction_results,
        }

        evidence_result = calculate_document_evidence_score(doc_stub)
        sample_size = evidence_result.get("sample_size")
        base_score = evidence_result.get("base_score")
        final_score = evidence_result.get("score")
        penalty_applied = evidence_result.get("penalty_applied")

        penalty_note = ""
        if penalty_applied:
            penalty_note = " (penalized for small sample size < 100)"

        confidence_text = (
            f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "unknown"
        )
        sample_text = str(sample_size) if sample_size is not None else "unknown"

        return (
            "Evidence strength context (computed):\n"
            f"- Evidence category: {category}\n"
            f"  Meaning: {EVIDENCE_CATEGORY_EXPLANATIONS.get(category, 'No description available.')}\n"
            f"- Evidence confidence: {confidence_text}\n"
            f"- Document evidence strength: {final_score}/5 (base {base_score}/5){penalty_note}\n"
            f"- Sample size (N): {sample_text}\n"
        )

    def _model_for_stage(self, stage: str) -> str:
        if not self.stage_models:
            return self.model_name
        stage_model = getattr(self.stage_models, stage, None)
        return stage_model or self.model_name

    @abstractmethod
    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract issues from the document. Implemented by subclasses."""
        pass

    @abstractmethod
    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract interventions from the document. Implemented by subclasses."""
        pass

    @abstractmethod
    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract mappings between issues and interventions. Implemented by subclasses."""
        pass

    @abstractmethod
    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract results for each intervention. Implemented by subclasses."""
        pass

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        """Default conclusions extraction using the standard prompt."""
        try:
            paper_id = state["paper_id"]
            interventions_json = (
                json.dumps(
                    [
                        intervention.model_dump()
                        for intervention in state["interventions"]
                    ],
                    indent=2,
                )
                if state["interventions"]
                else "No interventions"
            )

            result = await self._run_prompt_stage(
                CONCLUSIONS_PROMPT,
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                    "evidence_strength_context": self._build_evidence_strength_context(
                        state
                    ),
                },
                self._get_stage_tags("conclusions", paper_id),
                self._get_run_name("conclusions"),
                stage_name="conclusions",
                extra={"paper_id": paper_id},
            )
            conclusion = ConclusionItem(**result["conclusion"])
            logger.info(f"[{self.workflow_type.upper()}] Extracted conclusion")
            return {"conclusion": conclusion}
        except Exception as e:
            logger.error(f"[{self.workflow_type.upper()}] Conclusions failed: {e}")
            return {"conclusion": None, "error": str(e)}

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

        initial_state = WorkflowState(
            paper_id=paper_id,
            full_text=full_text,
            evidence_category=evidence_category,
            evidence_confidence=evidence_confidence,
            workflow_type=self.workflow_type,
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
                return self._empty_bundle(paper_id)

            conclusion = final_state.get("conclusion")

            return DocumentExtractionBundle(
                paper_id=paper_id,
                workflow_used=self.workflow_type,
                routing_reason="evidence_category",
                issues=final_state["issues"],
                interventions=final_state["interventions"],
                mappings=final_state["mappings"],
                results=final_state["results"],
                conclusion=conclusion,
                n_studies_included=final_state.get("n_studies_included"),
                sr_completeness_flag=final_state.get("sr_completeness_flag"),
            )

        except Exception as e:
            logger.error(f"Workflow failed for {paper_id}: {e}")
            return self._empty_bundle(paper_id)

    def _empty_bundle(self, paper_id: str) -> DocumentExtractionBundle:
        """Return an empty bundle on error."""
        return DocumentExtractionBundle(
            paper_id=paper_id,
            workflow_used=self.workflow_type,
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

    def _get_stage_tags(self, stage_name: str, paper_id: str) -> List[str]:
        """Build standardized tags for a workflow stage.

        Args:
            stage_name: The extraction stage (e.g., "issues", "interventions")
            paper_id: The paper identifier

        Returns:
            List of tags for Langfuse tracing
        """
        model_name = self._model_for_stage(stage_name)
        return [
            "component:extraction",
            f"component:extraction.{stage_name}",
            f"workflow:{self.workflow_type}",
            f"paper:{paper_id}",
            f"model:{model_name}",
        ]

    def _get_run_name(self, stage_name: str) -> str:
        """Build standardized run name for a workflow stage.

        Args:
            stage_name: The extraction stage (e.g., "issues", "interventions")

        Returns:
            Run name in format "{workflow_type}.extraction.{stage_name}"
        """
        return f"{self.workflow_type}.extraction.{stage_name}"

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
        stage_name: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a prompt stage with standard callbacks, tags, and metadata."""
        llm = self._llms.get(stage_name, self.llm)
        chain = prompt | llm | self.json_parser
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

    async def _validate_and_filter(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage: Post-hoc validation - filter items without valid quotes.

        Common validation logic for all workflows. Can be overridden by subclasses
        for workflow-specific validation (e.g., SR heterogeneity checking).
        """
        try:
            full_text = state["full_text"]
            workflow_tag = f"[{self.workflow_type.upper()}]"

            valid_issues, invalid_issues = self._split_by_grounded_quote(
                state["issues"], full_text
            )
            if invalid_issues:
                logger.warning(
                    f"{workflow_tag} Filtered {len(invalid_issues)} issues with ungrounded quotes"
                )

            valid_interventions, invalid_interventions = self._split_by_grounded_quote(
                state["interventions"], full_text
            )
            if invalid_interventions:
                logger.warning(
                    f"{workflow_tag} Filtered {len(invalid_interventions)} interventions with ungrounded quotes"
                )

            valid_issue_indices = {issue.idx for issue in valid_issues}
            valid_intervention_indices = {i.idx for i in valid_interventions}

            valid_mappings, invalid_mappings = self._split_mappings_by_grounded_quote(
                state["mappings"],
                valid_issue_indices,
                valid_intervention_indices,
                full_text,
            )
            if invalid_mappings:
                logger.warning(
                    f"{workflow_tag} Filtered {len(invalid_mappings)} mappings with invalid references or ungrounded quotes"
                )

            valid_results, invalid_results = self._split_results_by_grounded_quote(
                state["results"], valid_intervention_indices, full_text
            )
            if invalid_results:
                logger.warning(
                    f"{workflow_tag} Filtered {len(invalid_results)} results with invalid references or ungrounded quotes"
                )

            valid_conclusion = self._validate_conclusion(
                state.get("conclusion"), full_text
            )
            if state.get("conclusion") and not valid_conclusion:
                logger.warning(
                    f"{workflow_tag} Filtered conclusion: quote not grounded"
                )

            logger.info(
                f"{workflow_tag} Validation complete. Kept: {len(valid_issues)} issues, "
                f"{len(valid_interventions)} interventions, {len(valid_mappings)} mappings, "
                f"{len(valid_results)} results, {'1' if valid_conclusion else '0'} conclusion"
            )

            return {
                "issues": valid_issues,
                "interventions": valid_interventions,
                "mappings": valid_mappings,
                "results": valid_results,
                "conclusion": valid_conclusion,
            }

        except Exception as e:
            logger.error(f"[{self.workflow_type.upper()}] Validation failed: {e}")
            return {"error": f"Validation failed: {e}"}
