"""
LangGraph workflow for minimal 4-stage document extraction.
Implements: Issues → Interventions → Mapping → Results (per intervention loop) → Validation
"""

import json
import logging
from typing import Any, Dict, List, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.core.config import settings
from .prompts import (
    ISSUES_PROMPT,
    INTERVENTIONS_PROMPT,
    MAPPING_PROMPT,
    RESULTS_PROMPT,
    CONCLUSIONS_PROMPT,
)
from .schemas_langchain import (
    DocumentExtractionBundle,
    IssuesExtraction,
    InterventionsExtraction,
    MappingsExtraction,
    ResultsExtraction,
    ConclusionsExtraction,
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
    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: ConclusionItem | None
    error: str | None


class ExtractionWorkflow:
    """LangGraph workflow for document extraction."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for LangChain workflow")
        self.llm = ChatOpenAI(
            model=model, temperature=temperature, openai_api_key=settings.OPENAI_API_KEY
        )
        self.json_parser = JsonOutputParser()
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(WorkflowState)

        # Add nodes
        workflow.add_node("extract_issues", self._extract_issues)
        workflow.add_node("extract_interventions", self._extract_interventions)
        workflow.add_node("extract_mappings", self._extract_mappings)
        workflow.add_node("extract_results", self._extract_results)
        workflow.add_node("extract_conclusions", self._extract_conclusions)
        workflow.add_node("validate_and_filter", self._validate_and_filter)

        # Define the flow
        workflow.set_entry_point("extract_issues")
        workflow.add_edge("extract_issues", "extract_interventions")
        workflow.add_edge("extract_interventions", "extract_mappings")
        workflow.add_edge("extract_mappings", "extract_results")
        workflow.add_edge("extract_results", "extract_conclusions")
        workflow.add_edge("extract_conclusions", "validate_and_filter")
        workflow.add_edge("validate_and_filter", END)

        return workflow.compile()

    async def run(self, paper_id: str, full_text: str) -> DocumentExtractionBundle:
        """Run the complete extraction workflow."""
        initial_state = WorkflowState(
            paper_id=paper_id,
            full_text=full_text,
            issues=[],
            interventions=[],
            mappings=[],
            results=[],
            conclusion=None,
            error=None,
        )

        try:
            final_state = await self.workflow.ainvoke(initial_state)

            if final_state.get("error"):
                logger.error(f"Workflow error for {paper_id}: {final_state['error']}")
                # Return empty bundle on error
                return DocumentExtractionBundle(
                    paper_id=paper_id,
                    issues=[],
                    interventions=[],
                    mappings=[],
                    results=[],
                    conclusion=None,
                )

            return DocumentExtractionBundle(
                paper_id=paper_id,
                issues=final_state["issues"],
                interventions=final_state["interventions"],
                mappings=final_state["mappings"],
                results=final_state["results"],
                conclusion=final_state["conclusion"],
            )

        except Exception as e:
            logger.error(f"Workflow failed for {paper_id}: {e}")
            return DocumentExtractionBundle(
                paper_id=paper_id,
                issues=[],
                interventions=[],
                mappings=[],
                results=[],
                conclusion=None,
            )

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage A: Extract issues."""
        try:
            chain = ISSUES_PROMPT | self.llm | self.json_parser
            result = await chain.ainvoke({"full_text": state["full_text"]})

            extraction = IssuesExtraction(**result)
            logger.info(f"Extracted {len(extraction.issues)} issues")

            return {"issues": extraction.issues}

        except Exception as e:
            logger.error(f"Issues extraction failed: {e}")
            return {"issues": [], "error": f"Issues extraction failed: {e}"}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage B: Extract interventions."""
        try:
            chain = INTERVENTIONS_PROMPT | self.llm | self.json_parser
            result = await chain.ainvoke({"full_text": state["full_text"]})

            extraction = InterventionsExtraction(**result)
            logger.info(f"Extracted {len(extraction.interventions)} interventions")

            return {"interventions": extraction.interventions}

        except Exception as e:
            logger.error(f"Interventions extraction failed: {e}")
            return {
                "interventions": [],
                "error": f"Interventions extraction failed: {e}",
            }

    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage C: Extract mappings between issues and interventions."""
        try:
            if not state["issues"] or not state["interventions"]:
                return {"mappings": []}

            issues_json = json.dumps(
                {"issues": [issue.model_dump() for issue in state["issues"]]}
            )
            interventions_json = json.dumps(
                {
                    "interventions": [
                        intervention.model_dump()
                        for intervention in state["interventions"]
                    ]
                }
            )

            chain = MAPPING_PROMPT | self.llm | self.json_parser
            result = await chain.ainvoke(
                {
                    "full_text": state["full_text"],
                    "issues_json": issues_json,
                    "interventions_json": interventions_json,
                }
            )

            extraction = MappingsExtraction(**result)
            logger.info(f"Extracted {len(extraction.mappings)} mappings")

            return {"mappings": extraction.mappings}

        except Exception as e:
            logger.error(f"Mappings extraction failed: {e}")
            return {"mappings": [], "error": f"Mappings extraction failed: {e}"}

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage D: Extract results per intervention."""
        try:
            if not state["interventions"]:
                return {"results": []}

            all_results = []
            chain = RESULTS_PROMPT | self.llm | self.json_parser

            # Process each intervention
            for intervention in state["interventions"]:
                try:
                    one_intervention_json = json.dumps(intervention.model_dump())

                    result = await chain.ainvoke(
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": one_intervention_json,
                        }
                    )

                    extraction = ResultsExtraction(**result)

                    # Ensure intervention_idx is set correctly
                    for res in extraction.results:
                        res.intervention_idx = intervention.idx

                    all_results.extend(extraction.results)

                except Exception as e:
                    logger.warning(
                        f"Results extraction failed for intervention {intervention.idx}: {e}"
                    )
                    continue

            logger.info(
                f"Extracted {len(all_results)} results across {len(state['interventions'])} interventions"
            )
            return {"results": all_results}

        except Exception as e:
            logger.error(f"Results extraction failed: {e}")
            return {"results": [], "error": f"Results extraction failed: {e}"}

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage E: Extract study conclusions with evidence strength and impact assessment."""
        try:
            # Prepare interventions context as JSON string
            interventions_json = (
                json.dumps(
                    [
                        intervention.model_dump()
                        for intervention in state["interventions"]
                    ],
                    indent=2,
                )
                if state["interventions"]
                else "No interventions extracted"
            )

            chain = CONCLUSIONS_PROMPT | self.llm | self.json_parser
            result = await chain.ainvoke(
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                }
            )

            extraction = ConclusionsExtraction(**result)
            logger.info("Extracted study conclusion with evidence assessment")

            return {"conclusion": extraction.conclusion}

        except Exception as e:
            logger.error(f"Conclusions extraction failed: {e}")
            return {"conclusion": None, "error": f"Conclusions extraction failed: {e}"}

    def _fuzzy_quote_match(
        self, quote: str, full_text: str, threshold: float = 0.7
    ) -> bool:
        """Check if a quote has substantial overlap with the full text."""
        if not quote or not full_text:
            return False

        # First try exact match (fastest)
        if quote.strip() in full_text:
            return True

        # Normalize both texts (remove extra whitespace, line breaks)
        import re

        def normalize_text(text: str) -> str:
            # Remove extra whitespace and normalize line breaks
            text = re.sub(r"\s+", " ", text.strip())
            return text.lower()

        normalized_quote = normalize_text(quote)
        normalized_full_text = normalize_text(full_text)

        # Try normalized exact match
        if normalized_quote in normalized_full_text:
            return True

        # For longer quotes, check if most of the content is present
        if len(normalized_quote) > 50:
            # Split into words and check overlap
            quote_words = set(normalized_quote.split())
            full_text_words = set(normalized_full_text.split())

            # Remove common words that don't add semantic value
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

        # For shorter quotes, be more strict but still allow some flexibility
        else:
            # Check if key phrases exist
            words = normalized_quote.split()
            if len(words) >= 4:
                # Check if first 4 words appear together somewhere
                phrase = " ".join(words[:4])
                return phrase in normalized_full_text
            else:
                # For very short quotes, require exact match
                return normalized_quote in normalized_full_text

    async def _validate_and_filter(self, state: WorkflowState) -> Dict[str, Any]:
        """Post-hoc validation: Filter items without valid quotes and check references."""
        try:
            full_text = state["full_text"]

            # Filter issues: keep only those with quotes that exist in text
            valid_issues = []
            for issue in state["issues"]:
                if issue.supporting_quote and self._fuzzy_quote_match(
                    issue.supporting_quote, full_text
                ):
                    valid_issues.append(issue)
                else:
                    logger.warning(
                        f"Filtered out issue {issue.idx}: quote not sufficiently grounded"
                    )

            # Filter interventions: keep only those with quotes that exist in text
            valid_interventions = []
            for intervention in state["interventions"]:
                if intervention.supporting_quote and self._fuzzy_quote_match(
                    intervention.supporting_quote, full_text
                ):
                    valid_interventions.append(intervention)
                else:
                    logger.warning(
                        f"Filtered out intervention {intervention.idx}: quote not sufficiently grounded"
                    )

            # Filter mappings: keep only those with valid indices and quotes
            valid_mappings = []
            valid_issue_indices = {issue.idx for issue in valid_issues}
            valid_intervention_indices = {
                intervention.idx for intervention in valid_interventions
            }

            for mapping in state["mappings"]:
                if (
                    mapping.issue_idx in valid_issue_indices
                    and mapping.intervention_idx in valid_intervention_indices
                    and mapping.supporting_quote
                    and self._fuzzy_quote_match(mapping.supporting_quote, full_text)
                ):
                    valid_mappings.append(mapping)
                else:
                    logger.warning(
                        f"Filtered out mapping {mapping.issue_idx}->{mapping.intervention_idx}"
                    )

            # Filter results: keep only those with valid intervention indices and quotes
            valid_results = []
            for result in state["results"]:
                if (
                    result.intervention_idx in valid_intervention_indices
                    and result.supporting_quote
                    and self._fuzzy_quote_match(result.supporting_quote, full_text)
                ):
                    valid_results.append(result)
                else:
                    logger.warning(
                        f"Filtered out result for intervention {result.intervention_idx}"
                    )

            # Validate conclusion if it exists
            valid_conclusion = None
            if state.get("conclusion"):
                conclusion = state["conclusion"]
                if conclusion.supporting_quote and self._fuzzy_quote_match(
                    conclusion.supporting_quote, full_text
                ):
                    valid_conclusion = conclusion
                else:
                    logger.warning(
                        "Filtered out conclusion: quote not sufficiently grounded"
                    )

            logger.info(
                f"Validation complete. Kept: {len(valid_issues)} issues, "
                f"{len(valid_interventions)} interventions, {len(valid_mappings)} mappings, "
                f"{len(valid_results)} results, "
                f"{'1' if valid_conclusion else '0'} conclusion"
            )

            return {
                "issues": valid_issues,
                "interventions": valid_interventions,
                "mappings": valid_mappings,
                "results": valid_results,
                "conclusion": valid_conclusion,
            }

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"error": f"Validation failed: {e}"}
