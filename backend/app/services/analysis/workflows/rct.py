"""
RCT Extraction Workflow.

Optimized for extracting data from individual RCTs and quasi-experimental studies.
"""

import json
import logging
from typing import Any, Dict

from .base import BaseExtractionWorkflow, WorkflowState
from ..prompts import (
    ISSUES_PROMPT,
    INTERVENTIONS_PROMPT,
    MAPPING_PROMPT,
    RESULTS_PROMPT,
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


class RCTExtractionWorkflow(BaseExtractionWorkflow):
    """Extraction workflow optimized for RCTs and quasi-experimental studies."""

    workflow_type = "rct"

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage A: Extract issues."""
        try:
            paper_id = state["paper_id"]
            result = await self._run_prompt_stage(
                ISSUES_PROMPT,
                {"full_text": state["full_text"]},
                self._get_stage_tags("issues", paper_id),
                self._get_run_name("issues"),
                extra={"paper_id": paper_id},
            )

            extraction = IssuesExtraction(**result)
            logger.info(f"[RCT] Extracted {len(extraction.issues)} issues")

            return {"issues": extraction.issues}

        except Exception as e:
            logger.error(f"[RCT] Issues extraction failed: {e}")
            return {"issues": [], "error": f"Issues extraction failed: {e}"}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage B: Extract interventions."""
        try:
            paper_id = state["paper_id"]
            result = await self._run_prompt_stage(
                INTERVENTIONS_PROMPT,
                {"full_text": state["full_text"]},
                self._get_stage_tags("interventions", paper_id),
                self._get_run_name("interventions"),
                extra={"paper_id": paper_id},
            )

            extraction = InterventionsExtraction(**result)

            logger.info(
                f"[RCT] Extracted {len(extraction.interventions)} interventions"
            )

            return {"interventions": extraction.interventions}

        except Exception as e:
            logger.error(f"[RCT] Interventions extraction failed: {e}")
            return {
                "interventions": [],
                "error": f"Interventions extraction failed: {e}",
            }

    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage C: Extract mappings between issues and interventions."""
        try:
            if not state["issues"] or not state["interventions"]:
                return {"mappings": []}

            paper_id = state["paper_id"]
            issues_json = self._serialize_for_prompt(state["issues"], "issues")
            interventions_json = self._serialize_for_prompt(
                state["interventions"], "interventions"
            )

            result = await self._run_prompt_stage(
                MAPPING_PROMPT,
                {
                    "full_text": state["full_text"],
                    "issues_json": issues_json,
                    "interventions_json": interventions_json,
                },
                self._get_stage_tags("mappings", paper_id),
                self._get_run_name("mappings"),
                extra={"paper_id": paper_id},
            )

            extraction = MappingsExtraction(**result)
            logger.info(f"[RCT] Extracted {len(extraction.mappings)} mappings")

            return {"mappings": extraction.mappings}

        except Exception as e:
            logger.error(f"[RCT] Mappings extraction failed: {e}")
            return {"mappings": [], "error": f"Mappings extraction failed: {e}"}

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage D: Extract results per intervention."""
        try:
            if not state["interventions"]:
                return {"results": []}

            paper_id = state["paper_id"]
            tags = self._get_stage_tags("results", paper_id)
            all_results = []

            # Process each intervention
            for intervention in state["interventions"]:
                try:
                    one_intervention_json = json.dumps(intervention.model_dump())

                    result = await self._run_prompt_stage(
                        RESULTS_PROMPT,
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": one_intervention_json,
                        },
                        tags,
                        self._get_run_name("results"),
                        extra={
                            "paper_id": paper_id,
                            "intervention_idx": intervention.idx,
                        },
                    )

                    extraction = ResultsExtraction(**result)

                    # Set fields for RCT workflow
                    for res in extraction.results:
                        res.intervention_idx = intervention.idx
                        res.estimate_level = "study"

                    all_results.extend(extraction.results)

                except Exception as e:
                    logger.warning(
                        f"[RCT] Results extraction failed for intervention {intervention.idx}: {e}"
                    )
                    continue

            logger.info(
                f"[RCT] Extracted {len(all_results)} results across "
                f"{len(state['interventions'])} interventions"
            )
            return {"results": all_results}

        except Exception as e:
            logger.error(f"[RCT] Results extraction failed: {e}")
            return {"results": [], "error": f"Results extraction failed: {e}"}

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        """Stage E: Extract study conclusions with evidence strength assessment."""
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
                else "No interventions extracted"
            )

            result = await self._run_prompt_stage(
                CONCLUSIONS_PROMPT,
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                },
                self._get_stage_tags("conclusions", paper_id),
                self._get_run_name("conclusions"),
                extra={"paper_id": paper_id},
            )

            extraction = ConclusionsExtraction(**result)
            logger.info("[RCT] Extracted study conclusion with evidence assessment")

            return {"conclusion": extraction.conclusion}

        except Exception as e:
            logger.error(f"[RCT] Conclusions extraction failed: {e}")
            return {"conclusion": None, "error": f"Conclusions extraction failed: {e}"}

    # Uses base class _validate_and_filter - no RCT-specific validation needed
