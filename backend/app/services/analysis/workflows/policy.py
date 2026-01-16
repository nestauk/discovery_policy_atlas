"""
Policy Extraction Workflow.

Optimized for extracting claim-level information from policy documents,
qualitative evidence, and expert commentary.
"""

import json
import logging
from typing import Any, Dict

from .base import BaseExtractionWorkflow, WorkflowState
from ..prompts import (
    POLICY_ISSUES_PROMPT,
    POLICY_INTERVENTIONS_PROMPT,
    POLICY_RESULTS_PROMPT,
    MAPPING_PROMPT,
    CONCLUSIONS_PROMPT,
)
from ..schemas_langchain import (
    IssuesExtraction,
    InterventionsExtraction,
    MappingsExtraction,
    ResultsExtraction,
    ConclusionsExtraction,
)

logger = logging.getLogger(__name__)


class PolicyExtractionWorkflow(BaseExtractionWorkflow):
    """Workflow for policy syntheses, qualitative evidence, and expert opinion."""

    workflow_type = "policy"

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            tags = [
                "component:extraction",
                "component:extraction.issues",
                "workflow:policy",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]
            result = await self._run_prompt_stage(
                POLICY_ISSUES_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "policy.extraction.issues",
                extra={"paper_id": state["paper_id"]},
            )
            extraction = IssuesExtraction(**result)
            logger.info(f"[POLICY] Extracted {len(extraction.issues)} issues")
            return {"issues": extraction.issues}
        except Exception as e:
            logger.error(f"[POLICY] Issues extraction failed: {e}")
            return {"issues": [], "error": f"Issues extraction failed: {e}"}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            tags = [
                "component:extraction",
                "component:extraction.interventions",
                "workflow:policy",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]
            result = await self._run_prompt_stage(
                POLICY_INTERVENTIONS_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "policy.extraction.interventions",
                extra={"paper_id": state["paper_id"]},
            )
            for item in result.get("interventions", []) or []:
                if item.get("implementation_level") in ("null", ""):
                    item["implementation_level"] = None
            extraction = InterventionsExtraction(**result)
            for intervention in extraction.interventions:
                intervention.intervention_semantic_type = "policy_measure"
            logger.info(
                f"[POLICY] Extracted {len(extraction.interventions)} interventions"
            )
            return {"interventions": extraction.interventions}
        except Exception as e:
            logger.error(f"[POLICY] Interventions extraction failed: {e}")
            return {
                "interventions": [],
                "error": f"Interventions extraction failed: {e}",
            }

    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            if not state["issues"] or not state["interventions"]:
                return {"mappings": []}

            tags = [
                "component:extraction",
                "component:extraction.mappings",
                "workflow:policy",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]
            result = await self._run_prompt_stage(
                MAPPING_PROMPT,
                {
                    "full_text": state["full_text"],
                    "issues_json": self._serialize_for_prompt(
                        state["issues"], "issues"
                    ),
                    "interventions_json": self._serialize_for_prompt(
                        state["interventions"], "interventions"
                    ),
                },
                tags,
                "policy.extraction.mappings",
                extra={"paper_id": state["paper_id"]},
            )
            extraction = MappingsExtraction(**result)
            logger.info(f"[POLICY] Extracted {len(extraction.mappings)} mappings")
            return {"mappings": extraction.mappings}
        except Exception as e:
            logger.error(f"[POLICY] Mappings extraction failed: {e}")
            return {"mappings": [], "error": f"Mappings extraction failed: {e}"}

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            if not state["interventions"]:
                return {"results": []}

            all_results = []
            for intervention in state["interventions"]:
                try:
                    tags = [
                        "component:extraction",
                        "component:extraction.results",
                        "workflow:policy",
                        f"paper:{state['paper_id']}",
                        f"model:{self.model_name}",
                    ]
                    result = await self._run_prompt_stage(
                        POLICY_RESULTS_PROMPT,
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": json.dumps(
                                intervention.model_dump()
                            ),
                        },
                        tags,
                        "policy.extraction.results",
                        extra={
                            "paper_id": state["paper_id"],
                            "intervention_idx": intervention.idx,
                        },
                    )
                    for item in result.get("results", []) or []:
                        if not item.get("result_text"):
                            item["result_text"] = (
                                item.get("claim_text")
                                or item.get("outcome_variable")
                                or ""
                            )
                    extraction = ResultsExtraction(**result)
                    for res in extraction.results:
                        res.intervention_idx = intervention.idx
                        res.estimate_level = "claim"
                    all_results.extend(extraction.results)
                except Exception as e:
                    logger.warning(
                        f"[POLICY] Results extraction failed for intervention {intervention.idx}: {e}"
                    )
                    continue

            logger.info(
                f"[POLICY] Extracted {len(all_results)} results across "
                f"{len(state['interventions'])} interventions"
            )
            return {"results": all_results}
        except Exception as e:
            logger.error(f"[POLICY] Results extraction failed: {e}")
            return {"results": [], "error": f"Results extraction failed: {e}"}

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            interventions_json = (
                json.dumps([i.model_dump() for i in state["interventions"]], indent=2)
                if state["interventions"]
                else "No interventions extracted"
            )
            tags = [
                "component:extraction",
                "component:extraction.conclusions",
                "workflow:policy",
                f"paper:{state['paper_id']}",
                f"model:{self.model_name}",
            ]
            result = await self._run_prompt_stage(
                CONCLUSIONS_PROMPT,
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                },
                tags,
                "policy.extraction.conclusions",
                extra={"paper_id": state["paper_id"]},
            )
            extraction = ConclusionsExtraction(**result)
            logger.info("[POLICY] Extracted conclusion")
            return {"conclusion": extraction.conclusion}
        except Exception as e:
            logger.error(f"[POLICY] Conclusions extraction failed: {e}")
            return {"conclusion": None, "error": f"Conclusions extraction failed: {e}"}

    # Uses base class _validate_and_filter - no policy-specific validation needed
