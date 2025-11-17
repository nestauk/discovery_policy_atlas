"""
Relevance and document type classification service for the analysis pipeline.

This service evaluates documents based on title and abstract to determine:
1. Relevance to the user's query
2. Document type classification (research paper, policy document, other)
3. Confidence scores and reasoning

Based on the screening service pattern but optimized for the analysis workflow.
"""

import pandas as pd
from typing import Dict, Optional
import asyncio
from datetime import datetime
from app.utils.llm import batch_check
import logging
from pathlib import Path
from .prompts import RELEVANCE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class RelevanceService:
    """
    Service for determining document relevance and type classification.

    Evaluates documents using title and abstract against the user query to:
    - Determine relevance (boolean + confidence + reasoning)
    - Classify document type (research_paper | policy_document | other)
    """

    def __init__(
        self,
        query: str,
        export_dir: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.query = query
        self.export_dir = Path(export_dir) if export_dir else Path("./temp")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.project_id = project_id
        self.user_id = user_id

        # System message for relevance and document type assessment
        self.system_message = RELEVANCE_SYSTEM_PROMPT(query)

        # Output fields for LLM processing
        self.fields = [
            {
                "name": "is_relevant",
                "type": "bool",
                "description": "Is this document relevant to the search query?",
            },
            {
                "name": "relevance_confidence",
                "type": "float",
                "description": "Confidence score from 0.0 to 1.0 for the relevance assessment",
            },
            {
                "name": "relevance_reason",
                "type": "str",
                "description": "Brief explanation (1-2 sentences) of why the document is or isn't relevant to the query",
            },
            {
                "name": "top_line",
                "type": "str",
                "description": "A concise, one-sentence top line summary with 15 words max, that clearly states the main takeaway or insight as it directly answers the research question or search query. Use clear, declarative language without introductory phrases (e.g. avoid 'This document outlines...'). Focus on delivering the core message or conclusion in plain terms, as if highlighting the key point for an executive summary.",
            },
            {
                "name": "document_type",
                "type": "str",
                "description": "Document type classification: 'research_paper' for studies/experiments/trials/data analyses, 'reviews' for reviews/meta-analyses/systematic reviews, 'policy_document' for policy recommendations/guidelines/frameworks, or 'other' for announcements/transcripts/opinion pieces",
            },
            {
                "name": "document_type_reason",
                "type": "str",
                "description": "Brief explanation (1 sentence) of why the document was classified as this type",
            },
        ]

    async def check_relevance(self, references_csv_path: str) -> str:
        """
        Check relevance for all documents in the references CSV.

        Args:
            references_csv_path: Path to the references CSV file

        Returns:
            Path to updated CSV file with relevance fields added
        """
        logger.info("Starting relevance checking for references")

        # Load references
        try:
            df = pd.read_csv(references_csv_path)
        except Exception as e:
            logger.error(f"Failed to load references CSV: {e}")
            return references_csv_path

        if df.empty:
            logger.warning("References CSV is empty, skipping relevance check")
            return references_csv_path

        # Prepare documents for LLM processing
        documents = {}
        for _, row in df.iterrows():
            doc_id = row.get("doc_id", str(row.name))
            title = row.get("title", "No title")
            abstract = row.get("abstract_or_summary", "No abstract available")

            # Combine title and abstract for analysis
            content = f"Title: {title}\n\nAbstract: {abstract}"
            documents[doc_id] = content

        if not documents:
            logger.warning("No documents to process for relevance check")
            return references_csv_path

        # Run relevance assessment
        session_name = f"relevance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            results_df = await self._screen_batch(documents, session_name)

            if results_df.empty:
                logger.warning("Relevance assessment returned no results")
                return references_csv_path

            # Merge results back into references DataFrame
            df = self._merge_relevance_results(df, results_df)

            # Save updated CSV (overwrite original to consolidate)
            df.to_csv(references_csv_path, index=False)

            relevant_count = (
                df["is_relevant"].sum() if "is_relevant" in df.columns else 0
            )
            logger.info(
                f"Relevance check complete: {relevant_count}/{len(df)} documents marked as relevant"
            )

            return references_csv_path

        except Exception as e:
            logger.error(f"Relevance checking failed: {e}")
            return references_csv_path

    def _merge_relevance_results(
        self, references_df: pd.DataFrame, results_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge relevance results back into the references DataFrame."""
        # Create mapping from results
        results_dict = {}
        for _, row in results_df.iterrows():
            doc_id = row.get("id")
            if doc_id:
                results_dict[doc_id] = {
                    "is_relevant": row.get("is_relevant", False),
                    "relevance_confidence": row.get("relevance_confidence", 0.0),
                    "relevance_reason": row.get("relevance_reason", ""),
                    "top_line": row.get("top_line", ""),
                    "document_type": row.get("document_type", "other"),
                    "document_type_reason": row.get("document_type_reason", ""),
                }

        # Add relevance fields to references DataFrame
        for field in [
            "is_relevant",
            "relevance_confidence",
            "relevance_reason",
            "top_line",
            "document_type",
            "document_type_reason",
        ]:
            references_df[field] = None

        # Map results to references
        for idx, row in references_df.iterrows():
            doc_id = row.get("doc_id")
            if doc_id in results_dict:
                for field, value in results_dict[doc_id].items():
                    references_df.at[idx, field] = value
            else:
                # Default values for documents not processed
                references_df.at[idx, "is_relevant"] = False
                references_df.at[idx, "relevance_confidence"] = 0.0
                references_df.at[idx, "relevance_reason"] = "Not processed"
                references_df.at[idx, "top_line"] = "Not processed"
                references_df.at[idx, "document_type"] = "other"
                references_df.at[idx, "document_type_reason"] = "Not processed"

        return references_df

    async def _screen_batch(
        self, documents: Dict[str, str], session_name: str
    ) -> pd.DataFrame:
        """Screen a batch of documents using the LLM processor."""
        if not documents:
            return pd.DataFrame()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.export_dir / f"relevance_{session_name}_{timestamp}.jsonl"

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
                "is_relevant": False,
                "relevance_confidence": 0.0,
                "relevance_reason": "",
                "top_line": "",
                "document_type": "other",
                "document_type_reason": "",
            }

            for col, default_value in expected_defaults.items():
                if col not in df.columns:
                    df[col] = default_value

            # Convert to proper types
            df["is_relevant"] = df["is_relevant"].astype(bool)
            df["relevance_confidence"] = pd.to_numeric(
                df["relevance_confidence"], errors="coerce"
            ).fillna(0.0)

            return df

        except Exception as e:
            logger.error(f"Relevance screening failed: {str(e)}")
            return pd.DataFrame(
                columns=[
                    "id",
                    "is_relevant",
                    "relevance_confidence",
                    "relevance_reason",
                    "top_line",
                    "document_type",
                    "document_type_reason",
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
            output_path=output_path,
            system_message=self.system_message,
            session_name=None,
            output_fields=self.fields,
            component_tags=[
                "component:relevance",
                "component:relevance.batch_check",
            ],
            policy_project_id=self.project_id,
            policy_user_id=self.user_id,
            run_name="relevance.batch_check",
        )

        # Run relevance assessment
        processor.run(documents, batch_size=25, sleep_time=0.5)

    def add_acquisition_tracking_columns(self, references_csv_path: str) -> str:
        """
        Add acquisition and extraction tracking columns to the references CSV.

        Args:
            references_csv_path: Path to references CSV with relevance data

        Returns:
            Path to updated CSV file with tracking columns
        """
        try:
            df = pd.read_csv(references_csv_path)

            # Add acquisition tracking columns
            acquisition_columns = {
                "acquisition_status": "not_attempted",
                "acquisition_error": None,
                "full_text_available": False,
                "file_path": None,
                "extraction_status": "not_attempted",
                "extraction_error": None,
                "text_source": None,
            }

            for col, default_value in acquisition_columns.items():
                if col not in df.columns:
                    df[col] = default_value

            # Save updated CSV (overwrite the same file)
            df.to_csv(references_csv_path, index=False)

            logger.info(f"Added acquisition tracking columns to {references_csv_path}")
            return references_csv_path

        except Exception as e:
            logger.error(f"Failed to add tracking columns: {e}")
            return references_csv_path
