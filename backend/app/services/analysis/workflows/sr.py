"""SR Extraction Workflow for systematic reviews and meta-analyses."""

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from .base import BaseExtractionWorkflow, WorkflowState
from ..prompts import EXTRACTION_SYSTEM_PROMPT, MAPPING_PROMPT, CONCLUSIONS_PROMPT
from ..schemas_langchain import (
    IssuesExtraction,
    InterventionsExtraction,
    MappingsExtraction,
    ResultsExtraction,
    ConclusionsExtraction,
)

logger = logging.getLogger(__name__)

# SR-specific prompts
SR_ISSUES_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Extract 1–3 PROBLEM STATEMENTS/ISSUES from this systematic review.

Schema:
{{"issues":[{{"idx":0,"label":"...","explanation":"...","supporting_quote":"..."}}], "coverage_note":"string|null"}}

Rules:
- MECE: Merge overlaps; avoid duplicates; prefer concise scientific labels.
- Focus on BROADER PROBLEMS that motivated the research (e.g., "high autism rates", "lack of early interventions", "poor treatment outcomes").
- DO NOT include study-specific findings or results (e.g., "this study found no effect") - those belong in results.
- AVOID generic research gaps like "need for more research" - focus on real-world problems.
- explanation: Provide 1-2 sentences contextualizing the issue beyond the quote (based on the information in the systematic review).
- Keep only concrete issues explicitly supported by the text.

Paper text:
{full_text}""",
        ),
    ]
)

SR_INTERVENTIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Extract 2–6 INTERVENTION CATEGORIES that are reviewed and form the main focus of this systematic review..

Schema:
{{"interventions":[{{"idx":0,"name":"...","type":"...","description":"...","geographic_scope":"...","population_intervened":["..."]|null,"evidence_volume":"...","supporting_quote":"..."}}], "coverage_note":"string"}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, no overlapping entries; merge variants.
- Focus exclusively on ACTIVE INTERVENTION CATEGORIES only (i.e. treatments, programmes, or policies under evaluation) 
- DO NOT include control groups, placebo groups, or "no intervention" conditions as interventions.
- Include attention control arms only if they involve active components (e.g., alternative treatments).
- Intervention descriptions must paraphrase only information explicitly stated in the supporting quote. Do not infer mechanisms, intensity, duration, or effectiveness.
- Extract INTERVENTION CATEGORIES as grouped in the review (not individual studies).
- DO NOT include interventions that are not evaluated, are not a primary focus, or are mentioned only in passing.
- If required information for a field is not reported at the category level, return "null" for that field.

Population Fields:
- population_intervened: The population(s) targeted across included studies within the intervention category (e.g. ["adults with depression", "children and adolescents"]). Use abstracted labels; do not infer specifics.
- evidence_volume: The volume of evidence supporting the intervention category (e.g. “5 RCTs”, “12 studies”), only if explicitly reported.

Paper text:
{full_text}""",
        ),
    ]
)

SR_RESULTS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """For ONLY the intervention category below, extract POOLED/META-ANALYTIC RESULTS.

Intervention:
{one_intervention_json}

Schema:
{{"results":[{{"intervention_idx":0,"outcome_variable":"...","direction":"increase|decrease|null|mixed_or_unclear","effect_size_type":"...|null","effect_size":"...|null","uncertainty":"...|null","heterogeneity_I2":"...|null","tau2":"...|null","n_studies":int|null,"sample_size":int|null,"stratum_type":"...|null","stratum_value":"...|null","population_measured":"...|null","result_text":"...","supporting_quote":"..."}}]}}

Rules:
- Extract SEPARATE RESULT ROWS for each stratum (subgroup analysis, follow-up period, setting variant, etc.)
- Focus on AGGREGATED REVIEW-LEVEL RESULTS for this intervention category, not per-study data
- Each result row should correspond to a single pooled or aggregate effect estimate for ONE stratum

IMPORTANT - Outcome Variable vs Stratum:
- outcome_variable: The BASE outcome measure ONLY (e.g., "BMI", "weight", "blood pressure") - DO NOT include time points or subgroup info here
- stratum_type + stratum_value: Captures the CONDITIONS under which the result applies (e.g., follow-up period, age group, setting)
- WRONG: outcome_variable="BMI at 12 months"
- CORRECT: outcome_variable="BMI", stratum_type="follow-up period", stratum_value="12 months"
- WRONG: outcome_variable="BMI short term"
- CORRECT: outcome_variable="BMI", stratum_type="follow-up period", stratum_value="short term"

Sample Size Fields (IMPORTANT - extract these when mentioned in the text):
- n_studies: Number of studies pooled for this result (k), as an INTEGER (e.g., 3, not "3 studies")
- sample_size: Total participants across pooled studies (N), as an INTEGER (e.g., 605, not "605 participants")
- Look for phrases like "X studies", "k=X", "N=X", "X participants", "sample of X"

Stratum Fields (captures how results vary within an intervention):
- stratum_type: The dimension of variation (e.g., "follow-up period", "age subgroup", "setting", "intervention variant", "dosage", "comparison type")
- stratum_value: The specific value for this stratum (e.g., "12 months", "short term", "children 5-11 years", "school-based", "high dose")

Effect Size Fields:
- effect_size_type: Type of pooled estimate (e.g., "SMD", "pooled OR", "RR", "MD")
- effect_size: The numeric value (e.g., "-0.11", "0.85")
- uncertainty: Confidence interval (e.g., "95% CI -0.21 to -0.01")
- heterogeneity_I2: I² statistic if reported (e.g., "45%")
- tau2: τ² (between-study variance) if reported

Direction:
- "increase" for improvements/increases, "decrease" for reductions, "null" for no significant effect, "mixed_or_unclear" for conflicting results

Paper text:
{full_text}""",
        ),
    ]
)


class SRExtractionWorkflow(BaseExtractionWorkflow):
    """Workflow for Systematic Reviews: Issues → Interventions → Mappings → Results → Conclusions."""

    workflow_type = "sr"

    def _build_workflow(self) -> StateGraph:
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

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            tags = ["component:extraction", "workflow:sr", f"paper:{state['paper_id']}"]
            result = await self._run_prompt_stage(
                SR_ISSUES_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "sr.issues",
            )
            extraction = IssuesExtraction(**result)
            logger.info(f"[SR] Extracted {len(extraction.issues)} review questions")
            return {"issues": extraction.issues}
        except Exception as e:
            logger.error(f"[SR] Issues extraction failed: {e}")
            return {"issues": [], "error": str(e)}

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            tags = ["component:extraction", "workflow:sr", f"paper:{state['paper_id']}"]
            result = await self._run_prompt_stage(
                SR_INTERVENTIONS_PROMPT,
                {"full_text": state["full_text"]},
                tags,
                "sr.interventions",
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
            tags = ["component:extraction", "workflow:sr", f"paper:{state['paper_id']}"]
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
                "sr.mappings",
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
            all_results = []

            for intervention in state["interventions"]:
                try:
                    tags = [
                        "component:extraction",
                        "workflow:sr",
                        f"paper:{state['paper_id']}",
                    ]
                    result = await self._run_prompt_stage(
                        SR_RESULTS_PROMPT,
                        {
                            "full_text": state["full_text"],
                            "one_intervention_json": json.dumps(
                                intervention.model_dump()
                            ),
                        },
                        tags,
                        "sr.results",
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

    async def _extract_conclusions(self, state: WorkflowState) -> Dict[str, Any]:
        try:
            tags = ["component:extraction", "workflow:sr", f"paper:{state['paper_id']}"]
            interventions_json = (
                json.dumps([i.model_dump() for i in state["interventions"]], indent=2)
                if state["interventions"]
                else "No interventions"
            )
            result = await self._run_prompt_stage(
                CONCLUSIONS_PROMPT,
                {
                    "full_text": state["full_text"],
                    "interventions_json": interventions_json,
                },
                tags,
                "sr.conclusions",
            )
            extraction = ConclusionsExtraction(**result)
            logger.info("[SR] Extracted conclusion")
            return {"conclusion": extraction.conclusion}
        except Exception as e:
            logger.error(f"[SR] Conclusions failed: {e}")
            return {"conclusion": None, "error": str(e)}

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
