"""SR Extraction Workflow for systematic reviews and meta-analyses."""

import json
import logging
from typing import Any, Dict

from .base import BaseExtractionWorkflow, WorkflowState
from ..prompts import (
    SR_ISSUES_PROMPT,
    SR_INTERVENTIONS_PROMPT,
    SR_RESULTS_PROMPT,
    MAPPING_PROMPT,
)
from ..schemas_langchain import (
    IssuesExtraction,
    InterventionsExtraction,
    MappingsExtraction,
    ResultsExtraction,
)

logger = logging.getLogger(__name__)


class SRExtractionWorkflow(BaseExtractionWorkflow):
    """Workflow for Systematic Reviews and Meta-Analyses."""

    workflow_type = "sr"

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            paper_id = state["paper_id"]
            result = await self._run_prompt_stage(
                SR_ISSUES_PROMPT,
                {"full_text": state["full_text"]},
                self._get_stage_tags("issues", paper_id),
                self._get_run_name("issues"),
                extra={"paper_id": paper_id},
            )
            extraction = IssuesExtraction(**result)
            logger.info(f"[SR] Extracted {len(extraction.issues)} review questions")
            return {"issues": extraction.issues}
        except Exception as e:
            logger.error(f"[SR] Issues extraction failed: {e}")
            return {"issues": [], "error": str(e)}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            paper_id = state["paper_id"]
            result = await self._run_prompt_stage(
                SR_INTERVENTIONS_PROMPT,
                {"full_text": state["full_text"]},
                self._get_stage_tags("interventions", paper_id),
                self._get_run_name("interventions"),
                extra={"paper_id": paper_id},
            )
            extraction = InterventionsExtraction(**result)
            for intervention in extraction.interventions:
                intervention.intervention_semantic_type = "intervention_category"
            logger.info(
                f"[SR] Extracted {len(extraction.interventions)} intervention categories"
            )
            return {"interventions": extraction.interventions}
        except Exception as e:
            logger.error(f"[SR] Interventions extraction failed: {e}")
            return {"interventions": [], "error": str(e)}

    async def _extract_mappings(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            if not state["issues"] or not state["interventions"]:
                return {"mappings": []}
            paper_id = state["paper_id"]
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
                self._get_stage_tags("mappings", paper_id),
                self._get_run_name("mappings"),
                extra={"paper_id": paper_id},
            )
            extraction = MappingsExtraction(**result)
            logger.info(f"[SR] Extracted {len(extraction.mappings)} mappings")
            return {"mappings": extraction.mappings}
        except Exception as e:
            logger.error(f"[SR] Mappings extraction failed: {e}")
            return {"mappings": [], "error": str(e)}

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            if not state["interventions"]:
                return {"results": []}
            paper_id = state["paper_id"]
            tags = self._get_stage_tags("results", paper_id)
            all_results = []

            for intervention in state["interventions"]:
                try:
                    result = await self._run_prompt_stage(
                        SR_RESULTS_PROMPT,
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": json.dumps(
                                intervention.model_dump()
                            ),
                        },
                        tags,
                        self._get_run_name("results"),
                        extra={
                            "paper_id": paper_id,
                            "intervention_idx": intervention.idx,
                        },
                    )
                    extraction = ResultsExtraction(**result)
                    for res in extraction.results:
                        res.intervention_idx = intervention.idx
                        res.estimate_level = "pooled"
                    all_results.extend(extraction.results)
                except Exception as e:
                    logger.warning(
                        f"[SR] Results failed for intervention {intervention.idx}: {e}"
                    )

            logger.info(f"[SR] Extracted {len(all_results)} pooled results")
            return {"results": all_results}
        except Exception as e:
            logger.error(f"[SR] Results extraction failed: {e}")
            return {"results": [], "error": str(e)}

    async def _validate_and_filter(self, state: WorkflowState) -> Dict[str, Any]:
        """SR validation: base validation plus heterogeneity completeness check."""
        # Run base validation
        result = await super()._validate_and_filter(state)

        if "error" in result:
            return result

        # SR-specific: Check completeness (heterogeneity measures present?)
        valid_results = result.get("results", [])
        has_heterogeneity = any(r.heterogeneity_I2 or r.tau2 for r in valid_results)
        result["sr_completeness_flag"] = (
            "complete" if has_heterogeneity else "incomplete_heterogeneity"
        )

        logger.info(f"[SR] Completeness: {result['sr_completeness_flag']}")
        return result
