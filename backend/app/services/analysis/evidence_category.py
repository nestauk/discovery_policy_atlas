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

import pandas as pd
from typing import Dict, Optional
import asyncio
from datetime import datetime
from app.utils.llm import batch_check
import logging
from pathlib import Path
from .prompts import EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)


# Valid evidence categories
EVIDENCE_CATEGORIES = [
    "Systematic Review and Meta-Analysis",
    "RCTs and Quasi-Experimental Studies",
    "Observational Research Studies",
    "Modelling & Simulation",
    "Policy Syntheses & Guidance Documents",
    "Qualitative & Contextual Evidence",
    "Expert Opinion and Commentary",
    "Other (Non-evidence documents)",
    "Unknown / Insufficient information",
]


class EvidenceCategoryService:
    """
    Service for classifying documents into evidence categories.

    Evaluates documents using title and abstract to classify into a 9-category
    evidence hierarchy based on methodological strength.
    """

    def __init__(
        self,
        export_dir: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.export_dir = Path(export_dir) if export_dir else Path("./temp")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.project_id = project_id
        self.user_id = user_id
        self.model = model or getattr(settings, "EVIDENCE_CATEGORY_MODEL", "gpt-5.2")

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

    async def categorise_documents(
        self, references_csv_path: str, only_relevant: bool = True
    ) -> str:
        """
        Categorise evidence type for documents in the references CSV.

        Args:
            references_csv_path: Path to the references CSV file
            only_relevant: If True, only process documents where is_relevant=True

        Returns:
            Path to updated CSV file with evidence category fields added
        """
        logger.info("Starting evidence categorisation for references")

        # Load references
        try:
            df = pd.read_csv(references_csv_path)
        except Exception as e:
            logger.error(f"Failed to load references CSV: {e}")
            return references_csv_path

        if df.empty:
            logger.warning("References CSV is empty, skipping evidence categorisation")
            return references_csv_path

        # Filter to only relevant documents if requested
        if only_relevant and "is_relevant" in df.columns:
            docs_to_process = df[df["is_relevant"]].copy()
            skipped_count = len(df) - len(docs_to_process)
            logger.info(
                f"Evidence categorisation: processing {len(docs_to_process)} relevant documents, "
                f"skipping {skipped_count} irrelevant documents"
            )
        else:
            docs_to_process = df.copy()
            logger.info(
                f"Evidence categorisation: processing all {len(docs_to_process)} documents"
            )

        if docs_to_process.empty:
            logger.warning("No documents to process for evidence categorisation")
            return references_csv_path

        # Prepare documents for LLM processing
        documents = {}
        for _, row in docs_to_process.iterrows():
            doc_id = row.get("doc_id", str(row.name))
            documents[doc_id] = self._format_document(row)

        if not documents:
            logger.warning("No documents to process for evidence categorisation")
            return references_csv_path

        # Run evidence categorisation
        session_name = f"evidence_cat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            results_df = await self._screen_batch(documents, session_name)

            if results_df.empty:
                logger.warning("Evidence categorisation returned no results")
                return references_csv_path

            # Merge results back into references DataFrame
            df = self._merge_evidence_results(df, results_df)

            # Save updated CSV (overwrite original to consolidate)
            df.to_csv(references_csv_path, index=False)

            # Count categorised documents
            categorised_count = (
                df["evidence_category"].notna().sum()
                if "evidence_category" in df.columns
                else 0
            )
            logger.info(
                f"Evidence categorisation complete: {categorised_count} documents categorised"
            )

            return references_csv_path

        except Exception as e:
            logger.error(f"Evidence categorisation failed: {e}")
            return references_csv_path

    def _format_document(self, row: pd.Series) -> str:
        """Format a document row into prompt text."""
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
        """Merge evidence categorisation results back into the references DataFrame."""
        # Create mapping from results
        results_dict = {}
        for _, row in results_df.iterrows():
            doc_id = row.get("id")
            if doc_id:
                results_dict[doc_id] = {
                    "evidence_category": row.get(
                        "evidence_category", "Unknown / Insufficient information"
                    ),
                    "evidence_confidence": row.get("evidence_confidence", 0.0),
                    "evidence_category_reasoning": row.get(
                        "evidence_category_reasoning", ""
                    ),
                }

        # Add evidence category fields to references DataFrame
        for field in [
            "evidence_category",
            "evidence_confidence",
            "evidence_category_reasoning",
        ]:
            if field not in references_df.columns:
                references_df[field] = None

        # Map results to references
        for idx, row in references_df.iterrows():
            doc_id = row.get("doc_id")
            if doc_id in results_dict:
                for field, value in results_dict[doc_id].items():
                    references_df.at[idx, field] = value

        return references_df

    async def _screen_batch(
        self, documents: Dict[str, str], session_name: str
    ) -> pd.DataFrame:
        """Screen a batch of documents using the LLM processor."""
        if not documents:
            return pd.DataFrame()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = (
            self.export_dir / f"evidence_category_{session_name}_{timestamp}.jsonl"
        )

        try:
            # Run the batch processor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_batch_processor,
                documents,
                str(output_path),
                session_name,
            )

            # Check if file exists and has content
            if not output_path.exists():
                logger.error(f"Output file {output_path} was not created")
                return pd.DataFrame()

            if output_path.stat().st_size == 0:
                logger.error(f"Output file {output_path} is empty")
                return pd.DataFrame()

            # Read results
            try:
                df = pd.read_json(str(output_path), lines=True)
            except Exception as e:
                logger.error(f"Failed to read JSON file: {e}")
                with open(output_path, "r") as f:
                    logger.error(f"File contents: {f.read()}")
                raise

            # Ensure all expected columns exist with defaults
            expected_defaults = {
                "id": None,
                "evidence_category": "Unknown / Insufficient information",
                "evidence_confidence": 0.0,
                "evidence_category_reasoning": "",
            }

            for col, default_value in expected_defaults.items():
                if col not in df.columns:
                    df[col] = default_value

            # Convert to proper types
            df["evidence_confidence"] = pd.to_numeric(
                df["evidence_confidence"], errors="coerce"
            ).fillna(0.0)

            return df

        except Exception as e:
            logger.error(f"Evidence categorisation screening failed: {str(e)}")
            return pd.DataFrame(
                columns=[
                    "id",
                    "evidence_category",
                    "evidence_confidence",
                    "evidence_category_reasoning",
                ]
            )

        finally:
            # Clean up
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {output_path}: {e}")

    def _run_batch_processor(
        self, documents: Dict[str, str], output_path: str, session_name: str
    ):
        """Run the batch processor synchronously."""
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

        # Run evidence categorisation
        processor.run(documents, batch_size=25, sleep_time=0.5)
