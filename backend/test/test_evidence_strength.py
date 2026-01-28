"""Unit tests for evidence strength calculation with sample size penalty."""

import asyncio
import logging

from app.services.analysis.evidence.strength import calculate_evidence_strength
from app.services.analysis.schemas_langchain import ConclusionItem, ImpactRating
from app.services.analysis.workflows.base import BaseExtractionWorkflow


class _TestWorkflow(BaseExtractionWorkflow):
    """Minimal workflow stub for testing computed evidence_strength persistence."""

    workflow_type = "test"

    def __init__(self):
        # Avoid OpenAI key requirement and LLM setup for this test workflow.
        self.model_name = "test"
        self.json_parser = None
        self.policy_project_id = None
        self.policy_user_id = None
        self._langfuse_session_id = None
        self._langfuse_handler = None
        self.workflow = self._build_workflow()

    async def _extract_issues(self, state):
        return {"issues": []}

    async def _extract_interventions(self, state):
        return {"interventions": []}

    async def _extract_mappings(self, state):
        return {"mappings": []}

    async def _extract_results(self, state):
        return {"results": []}

    async def _extract_conclusions(self, state):
        return {
            "conclusion": ConclusionItem(
                top_line_summary="Summary",
                detailed_explanation="Details",
                supporting_quote="Quote",
                predicted_impact=ImpactRating(
                    stars=3,
                    justification="Impact justification",
                    evidence_gap=None,
                ),
            )
        }


logger = logging.getLogger(__name__)


def _make_doc(
    category: str,
    confidence: float = 0.8,
    sample_size: int | None = None,
    doc_id: str | None = None,
) -> dict:
    """Helper to create test document dicts."""
    doc = {
        "evidence_category": category,
        "evidence_confidence": confidence,
    }
    if sample_size is not None:
        doc["sample_size"] = sample_size
    if doc_id is not None:
        doc["doc_id"] = doc_id
    return doc


class TestSampleSizePenalty:
    """Tests for the N<100 sample size penalty on causal evidence."""

    def test_small_sample_penalty_single_rct(self):
        """Single RCT with N<100 should get sample size penalty."""
        docs = [
            _make_doc("RCTs and Quasi-Experimental Studies", sample_size=50, doc_id="1")
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("single_rct_small_sample result=%s", result)
        assert result["base_rating"] == 4
        # Sample size penalty applied (4->3), single_rct cap is 3, doesn't reduce further
        assert result["stars"] == 3
        assert result["cap_applied"] == "small_sample"

    def test_small_sample_penalty_multiple_small_rcts(self):
        """Multiple RCTs all with N<100 should get sample size penalty."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=50, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=80, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("multiple_small_rcts result=%s", result)
        assert result["base_rating"] == 4
        assert result["cap_applied"] == "small_sample"
        assert result["stars"] == 3  # 4 -> 3 from sample size penalty

    def test_large_sample_exempts_from_penalty(self):
        """RCT with N>=100 should NOT trigger sample size penalty."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=150, doc_id="1"
            )
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("single_rct_large_sample result=%s", result)
        assert result["base_rating"] == 4
        # Only single-study cap, no sample size penalty
        assert result["cap_applied"] == "single_rct"
        assert result["stars"] == 3

    def test_one_large_sample_exempts_all(self):
        """If ANY RCT has N>=100, no sample size penalty applies."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=50, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=150, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("mixed_small_large_rcts result=%s", result)
        assert result["base_rating"] == 4
        # No sample size penalty because one study has N>=100
        assert result["cap_applied"] is None
        assert result["stars"] == 4

    def test_unknown_sample_sizes_excluded(self):
        """Documents with unknown (None) sample sizes don't trigger or prevent penalty."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=None, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=None, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("unknown_sample_sizes result=%s", result)
        assert result["base_rating"] == 4
        # No penalty because no known sample sizes
        assert result["cap_applied"] is None
        assert result["stars"] == 4

    def test_mixed_known_unknown_penalty_applies(self):
        """Known small sample + unknown should still trigger penalty."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=50, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=None, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("small_known_unknown result=%s", result)
        assert result["base_rating"] == 4
        # Penalty applies because ALL known samples are small
        assert result["cap_applied"] == "small_sample"
        assert result["stars"] == 3

    def test_observational_small_sample_penalty(self):
        """Observational studies with N<100 should also get penalty."""
        docs = [
            _make_doc("Observational Research Studies", sample_size=50, doc_id="1"),
            _make_doc("Observational Research Studies", sample_size=60, doc_id="2"),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("observational_small_sample result=%s", result)
        assert result["base_rating"] == 3
        assert result["cap_applied"] == "small_sample"
        assert result["stars"] == 2  # 3 -> 2

    def test_systematic_review_no_penalty(self):
        """Systematic reviews should NOT get sample size penalty."""
        docs = [
            _make_doc("Systematic Review and Meta-Analysis", sample_size=50, doc_id="1")
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("single_systematic_review result=%s", result)
        assert result["base_rating"] == 5
        # Only single-study cap for SR, no sample size penalty
        assert result["cap_applied"] == "single_srma"
        assert result["stars"] == 4

    def test_modelling_no_penalty(self):
        """Modelling studies should NOT get sample size penalty."""
        docs = [_make_doc("Modelling & Simulation", sample_size=50, doc_id="1")]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("modelling_no_penalty result=%s", result)
        assert result["base_rating"] == 2
        assert result["cap_applied"] is None
        assert result["stars"] == 2

    def test_boundary_n99_triggers_penalty(self):
        """N=99 should trigger penalty (strictly less than 100)."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=99, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=99, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("boundary_n99 result=%s", result)
        assert result["cap_applied"] == "small_sample"
        assert result["stars"] == 3

    def test_boundary_n100_no_penalty(self):
        """N=100 should NOT trigger penalty (threshold is strictly less than)."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=100, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=100, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("boundary_n100 result=%s", result)
        assert result["cap_applied"] is None
        assert result["stars"] == 4


class TestEvidenceStrengthBasics:
    """Basic tests for evidence strength calculation."""

    def test_no_qualifying_documents(self):
        """No documents meeting confidence threshold returns 0 stars."""
        docs = [_make_doc("RCTs and Quasi-Experimental Studies", confidence=0.3)]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("no_qualifying_documents result=%s", result)
        assert result["stars"] == 0
        assert result["cap_message"] == "No qualifying evidence"

    def test_empty_documents(self):
        """Empty document list returns 0 stars."""
        result = calculate_evidence_strength([], project_total_docs=10)

        logger.info("empty_documents result=%s", result)
        assert result["stars"] == 0


class TestEvidenceStrengthPersistence:
    """Ensure computed evidence strength is written into extraction results."""

    def test_conclusion_includes_evidence_strength(self):
        workflow = _TestWorkflow()

        bundle = asyncio.run(
            workflow.run(
                paper_id="paper-1",
                full_text="Quote",
                evidence_category="RCTs and Quasi-Experimental Studies",
                evidence_confidence=0.9,
            )
        )

        assert bundle.conclusion is not None
        evidence_strength = bundle.conclusion.evidence_strength
        assert evidence_strength is not None
        assert evidence_strength.stars == 4
        assert "Based on evidence category" in evidence_strength.justification

    def test_evidence_hierarchy(self):
        """Higher evidence types should yield higher base ratings."""
        sr_docs = [
            _make_doc("Systematic Review and Meta-Analysis", doc_id="1"),
            _make_doc("Systematic Review and Meta-Analysis", doc_id="2"),
        ]
        rct_docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=200, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=200, doc_id="2"
            ),
        ]
        obs_docs = [
            _make_doc("Observational Research Studies", sample_size=200, doc_id="1"),
            _make_doc("Observational Research Studies", sample_size=200, doc_id="2"),
        ]

        sr_result = calculate_evidence_strength(sr_docs, project_total_docs=10)
        rct_result = calculate_evidence_strength(rct_docs, project_total_docs=10)
        obs_result = calculate_evidence_strength(obs_docs, project_total_docs=10)

        logger.info(
            "evidence_hierarchy results=sr:%s rct:%s obs:%s",
            sr_result,
            rct_result,
            obs_result,
        )
        assert sr_result["base_rating"] == 5
        assert rct_result["base_rating"] == 4
        assert obs_result["base_rating"] == 3


class TestCapStacking:
    """Tests for penalty and cap stacking behavior."""

    def test_sample_penalty_then_single_study_cap(self):
        """Sample size penalty + single-study cap on observational (where they stack)."""
        # Use observational where single_obs cap is 2, so 3->2 from penalty then 2->2 from cap
        docs = [_make_doc("Observational Research Studies", sample_size=50, doc_id="1")]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        logger.info("cap_stacking_observational result=%s", result)
        # Base: 3, sample penalty: -1 -> 2, single_obs cap: 2 (doesn't reduce further)
        assert result["base_rating"] == 3
        assert result["stars"] == 2

    def test_sample_penalty_message(self):
        """Sample size penalty should have appropriate cap_message."""
        docs = [
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=50, doc_id="1"
            ),
            _make_doc(
                "RCTs and Quasi-Experimental Studies", sample_size=60, doc_id="2"
            ),
        ]
        result = calculate_evidence_strength(docs, project_total_docs=10)

        assert result["cap_applied"] == "small_sample"
        assert "sample sizes under 100" in result["cap_message"]
