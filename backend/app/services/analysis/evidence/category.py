"""
Evidence categorisation service for the analysis pipeline.

This service classifies documents into a 9-category evidence hierarchy based on
methodological strength, using the title, abstract, and metadata.

Categories (ordered by evidence strength):
1. Systematic Review and Meta-Analysis
2. RCTs and Quasi-Experimental Studies
3. Observational Research Studies
4. Modelling & Simulation
5. Policy Syntheses & Guidance Documents
6. Qualitative & Contextual Evidence
7. Expert Opinion and Commentary
8. Other (Non-evidence documents)
9. Unknown / Insufficient information

Based on R&D testing in testing/r_and_d/evidence_categorisation/.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from app.core.config import settings
from app.utils.llm import batch_check
from ..prompts import EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Category name used for documents excluded from evidence counts/UX.
NON_EVIDENCE_CATEGORY = "Other (Non-evidence documents)"


def is_non_evidence_document(doc: dict) -> bool:
    """Return True when a document is flagged as non-evidence."""
    return doc.get("evidence_category") == NON_EVIDENCE_CATEGORY


# Single source of truth for evidence categories.
# Each tuple: (full_name, key, score, short_name, bg_color, text_color)
# Rank is derived from list order (1-indexed).
_EVIDENCE_CATEGORY_DATA = [
    # (name, key, score, short_name, bg_color, text_color, explanation)
    (
        "Systematic Review and Meta-Analysis",
        "systematic_review",
        5,
        "Systematic Review",
        "#0F294A",
        "#FFFFFF",
        "Synthesizes multiple studies to provide the strongest evidence tier.",
    ),
    (
        "RCTs and Quasi-Experimental Studies",
        "rct",
        4,
        "RCT/Quasi-Exp",
        "#9A1BBE",
        "#FFFFFF",
        "Causal designs with controls; strongest primary-study evidence.",
    ),
    (
        "Observational Research Studies",
        "observational",
        3,
        "Observational",
        "#0000FF",
        "#FFFFFF",
        "Non-randomized evidence showing associations; weaker causal certainty.",
    ),
    (
        "Modelling & Simulation",
        "modelling",
        2,
        "Modelling",
        "#18A48C",
        "#FFFFFF",
        "Modelled or simulated evidence, not direct empirical outcomes.",
    ),
    (
        "Policy Syntheses & Guidance Documents",
        "policy",
        2,
        "Policy Guidance",
        "#97D9E3",
        "#111827",
        "Policy-focused synthesis or guidance rather than primary evidence.",
    ),
    (
        "Qualitative & Contextual Evidence",
        "qualitative",
        2,
        "Qualitative",
        "#A59BEE",
        "#111827",
        "Interview/qualitative/contextual evidence; rich but not causal.",
    ),
    (
        "Expert Opinion and Commentary",
        "opinion",
        1,
        "Expert Opinion",
        "#F6A4B7",
        "#111827",
        "Expert commentary without primary empirical testing.",
    ),
    (
        "Other (Non-evidence documents)",
        "other",
        0,
        "Other",
        "#F8F5F4",
        "#374151",
        "Not research evidence.",
    ),
    (
        "Unknown / Insufficient information",
        "unknown",
        0,
        "Unknown",
        "#F8F5F4",
        "#374151",
        "Insufficient information to classify evidence quality.",
    ),
]


# Derived mappings (generated once at module load)
EVIDENCE_CATEGORIES = [row[0] for row in _EVIDENCE_CATEGORY_DATA]
EVIDENCE_CATEGORY_SHORT_NAMES = {row[0]: row[3] for row in _EVIDENCE_CATEGORY_DATA}
EVIDENCE_CATEGORY_SCORES = {row[0]: row[2] for row in _EVIDENCE_CATEGORY_DATA}
EVIDENCE_CATEGORY_RANKS = {
    row[0]: rank for rank, row in enumerate(_EVIDENCE_CATEGORY_DATA, start=1)
}
EVIDENCE_CATEGORY_TO_KEY = {row[0]: row[1] for row in _EVIDENCE_CATEGORY_DATA}
EVIDENCE_CATEGORY_EXPLANATIONS = {row[0]: row[6] for row in _EVIDENCE_CATEGORY_DATA}

# Thresholds for evidence strength calculations
EVIDENCE_CONFIDENCE_THRESHOLD = 0.5
DENSITY_THRESHOLD = 0.025  # 2.5%
SMALL_SAMPLE_THRESHOLD = 100  # N < 100 triggers penalty for causal evidence

CAP_MESSAGES = {
    "single_srma": "Limited by single systematic review",
    "single_rct": "Limited by single experimental study",
    "single_obs": "Limited by single observational study",
    "density": "Limited by small evidence base",
    "small_sample": "All studies have sample sizes under 100, limiting statistical power",
}

# Evidence categories where sample size matters for causal inference
CAUSAL_EVIDENCE_CATEGORIES = {
    "RCTs and Quasi-Experimental Studies",
    "Observational Research Studies",
}


def get_evidence_categories_for_api() -> list[dict]:
    """Get evidence category data formatted for the API/frontend.

    Returns:
        List of dicts with all category data including display properties.
    """
    return [
        {
            "name": name,
            "key": key,
            "score": score,
            "rank": rank,
            "short_name": short_name,
            "bg_color": bg_color,
            "text_color": text_color,
        }
        for rank, (name, key, score, short_name, bg_color, text_color) in enumerate(
            _EVIDENCE_CATEGORY_DATA, start=1
        )
    ]


# TODO: Consider extracting common batch processing logic (shared with RelevanceService)
# if we add a third LLM-based service. See _screen_batch and _run_batch_processor.
class EvidenceCategoryService:
    """Classifies documents into a 9-category evidence hierarchy.

    Attributes:
        export_dir: Directory for temporary output files.
        project_id: Project identifier for tracking.
        user_id: User identifier for tracking.
        model: LLM model name for classification.
        batch_size: Number of documents per LLM batch.
        sleep_time: Delay between batches in seconds.
    """

    def __init__(
        self,
        export_dir: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: int = 25,
        sleep_time: float = 0.5,
    ):
        self.export_dir = Path(export_dir) if export_dir else Path("./temp")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.project_id = project_id
        self.user_id = user_id
        self.model = model or getattr(settings, "EVIDENCE_CATEGORY_MODEL", "gpt-5.2")
        self.batch_size = batch_size
        self.sleep_time = sleep_time

        self.system_message = EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT

        # Output fields for LLM processing
        self.fields = [
            {
                "name": "evidence_category",
                "type": "str",
                "description": (
                    "One of: 'Systematic Review and Meta-Analysis', "
                    "'RCTs and Quasi-Experimental Studies', "
                    "'Observational Research Studies', 'Modelling & Simulation', "
                    "'Policy Syntheses & Guidance Documents', "
                    "'Qualitative & Contextual Evidence', "
                    "'Expert Opinion and Commentary', 'Other (Non-evidence documents)', "
                    "'Unknown / Insufficient information'"
                ),
            },
            {
                "name": "evidence_confidence",
                "type": "float",
                "description": "Confidence score between 0.0 and 1.0",
            },
            {
                "name": "evidence_category_reasoning",
                "type": "str",
                "description": "Brief explanation (1-2 sentences) for the classification",
            },
        ]

    async def categorise_documents(self, references_csv_path: str) -> str:
        """Categorise evidence type for relevant documents in the CSV.

        Args:
            references_csv_path: Path to CSV with 'is_relevant' column.

        Returns:
            Path to updated CSV with evidence_category fields added.

        Raises:
            ValueError: If CSV is empty, missing 'is_relevant', or has no relevant docs.
        """
        logger.info("Starting evidence categorisation")

        try:
            df = pd.read_csv(references_csv_path)
        except Exception as e:
            logger.error(f"Failed to load references CSV: {e}")
            return references_csv_path

        if df.empty:
            raise ValueError("References CSV is empty")

        if "is_relevant" not in df.columns:
            raise ValueError("Missing 'is_relevant' column")

        docs_to_process = df[df["is_relevant"]].copy()
        if docs_to_process.empty:
            raise ValueError("No relevant documents to categorise")

        logger.info(f"Processing {len(docs_to_process)} relevant documents")

        documents = {
            row.get("doc_id", str(idx)): self._format_document(row)
            for idx, row in docs_to_process.iterrows()
        }

        try:
            results_df = await self._screen_batch(documents)
            if results_df.empty:
                logger.warning("Evidence categorisation returned no results")
                return references_csv_path

            df = self._merge_evidence_results(df, results_df)
            df.to_csv(references_csv_path, index=False)

            categorised = df["evidence_category"].notna().sum()
            logger.info(f"Categorised {categorised} documents")
            return references_csv_path

        except Exception as e:
            logger.error(f"Evidence categorisation failed: {e}")
            return references_csv_path

    def _format_document(self, row: pd.Series) -> str:
        """Format a DataFrame row into LLM prompt text."""
        title = row.get("title", "No title")
        abstract = row.get("abstract_or_summary", "No abstract available")
        source = row.get("source", "Unknown")
        doc_type = row.get("type", "Unknown")
        year = row.get("year", "Unknown")

        return f"""Classify the following document:

**Title**: {title}
**Abstract/Summary**: {abstract}
**Metadata**: Source: {source}, Type: {doc_type}, Year: {year}"""

    def _merge_evidence_results(
        self, references_df: pd.DataFrame, results_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge LLM results into references by doc_id."""
        results_df = results_df.set_index("id")
        fields = [
            "evidence_category",
            "evidence_confidence",
            "evidence_category_reasoning",
        ]

        for field in fields:
            references_df[field] = references_df["doc_id"].map(
                results_df[field].to_dict() if field in results_df.columns else {}
            )

        return references_df

    async def _screen_batch(self, documents: Dict[str, str]) -> pd.DataFrame:
        """Run LLM classification on documents and return results DataFrame."""
        if not documents:
            return pd.DataFrame()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.export_dir / f"evidence_category_{timestamp}.jsonl"

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._run_batch_processor, documents, str(output_path)
            )

            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error(f"Output file {output_path} missing or empty")
                return pd.DataFrame()

            df = pd.read_json(str(output_path), lines=True)
            df["evidence_confidence"] = pd.to_numeric(
                df["evidence_confidence"], errors="coerce"
            ).fillna(0.0)
            return df

        except Exception as e:
            logger.error(f"Screening failed: {e}")
            return pd.DataFrame()

        finally:
            if output_path.exists():
                output_path.unlink(missing_ok=True)

    def _run_batch_processor(self, documents: Dict[str, str], output_path: str):
        """Execute LLM batch processing synchronously (called via executor)."""
        processor = batch_check.LLMProcessor(
            model_name=self.model,
            output_path=output_path,
            system_message=self.system_message,
            session_name=None,
            output_fields=self.fields,
            component_tags=[
                "component:evidence_category",
                "component:evidence_category.batch_check",
            ],
            policy_project_id=self.project_id,
            policy_user_id=self.user_id,
            run_name="evidence_category.batch_check",
        )
        processor.run(documents, batch_size=self.batch_size, sleep_time=self.sleep_time)
