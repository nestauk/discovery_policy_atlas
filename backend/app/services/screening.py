import pandas as pd
from typing import Dict
import os
import asyncio
from datetime import datetime
from app.utils.llm import batch_check
import logging

logger = logging.getLogger(__name__)


class ScreeningService:
    def __init__(self, system_message: str, extra_fields: list[str] = None):
        self.system_message = system_message
        self.fields = [
            {
                "name": "is_relevant",
                "type": "bool",
                "description": "Is this paper/article relevant to the search query?",
            },
            {
                "name": "relevance_reason",
                "type": "str",
                "description": "Brief explanation of why it is or isn't relevant",
            },
            {
                "name": "top_line",
                "type": "str",
                "description": "A concise, one-sentence top line summary with 15 words max, that clearly states the main takeaway or insight as it directly answers the research question or search query. Use clear, declarative language without introductory phrases (e.g. avoid 'This document outlines...'). Focus on delivering the core message or conclusion in plain terms, as if highlighting the key point for an executive summary.",
            },
            {
                "name": "key_facts",
                "type": "str",
                "description": "A comma-separated list (1-2 items) of the most specific, quantitative facts reported by the source (e.g., numbers, percentages, dates).",
            },
            {
                "name": "policy_recommendations",
                "type": "str",
                "description": "A comma-separatedlist of concrete policy recommendations mentioned in the text, if any.",
            },
            {
                "name": "confidence",
                "type": "float",
                "description": "Confidence score from 0.0 to 1.0",
            },
        ]
        if extra_fields:
            for idx, field in enumerate(extra_fields, 1):
                self.fields.append(
                    {
                        "name": f"extra_field_{idx}",
                        "type": "str",
                        "description": f"User-specified extraction field: {field}",
                    }
                )

    async def screen_batch(
        self, documents: Dict[str, str], session_name: str
    ) -> pd.DataFrame:
        """Screen a batch of documents, return results as DataFrame"""

        if not documents:
            return pd.DataFrame()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"screening_{session_name}_{timestamp}.jsonl"

        try:
            # Run the batch processor in a thread pool since it's synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._run_batch_processor, documents, output_path, session_name
            )

            # Check if file exists and has content
            if not os.path.exists(output_path):
                logger.error(f"Output file {output_path} was not created")
                return pd.DataFrame()

            # Check file size
            if os.path.getsize(output_path) == 0:
                logger.error(f"Output file {output_path} is empty")
                return pd.DataFrame()

            # Read results with pandas
            try:
                df = pd.read_json(output_path, lines=True)
            except Exception as e:
                logger.error(f"Failed to read JSON file: {e}")
                # Try to read line by line for debugging
                with open(output_path, "r") as f:
                    logger.error(f"File contents: {f.read()}")
                raise

            # Ensure all expected columns exist with correct default types
            expected_defaults = {
                "id": None,
                "is_relevant": False,
                "relevance_reason": "",
                "top_line": "",
                "key_facts": [],
                "policy_recommendations": [],
                "confidence": None,
            }

            for col, default_value in expected_defaults.items():
                if col not in df.columns:
                    if isinstance(default_value, list):
                        df[col] = [list() for _ in range(len(df))]
                    else:
                        df[col] = default_value

            # Normalize list-typed columns in case they came as strings/nulls
            for list_col in ["key_facts", "policy_recommendations"]:
                if list_col in df.columns:
                    df[list_col] = df[list_col].apply(
                        lambda v: v
                        if isinstance(v, list)
                        else (
                            [] if pd.isna(v) else ([v] if v not in ("", None) else [])
                        )
                    )

            # Convert to proper types
            df["is_relevant"] = df["is_relevant"].astype(bool)
            df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"Screening failed: {str(e)}")
            # Return empty DataFrame on error
            return pd.DataFrame(
                columns=[
                    "id",
                    "is_relevant",
                    "relevance_reason",
                    "top_line",
                    "key_facts",
                    "policy_recommendations",
                    "confidence",
                ]
            )

        finally:
            # Clean up
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {output_path}: {e}")

    def _run_batch_processor(
        self, documents: Dict[str, str], output_path: str, session_name: str
    ):
        """Run the batch processor synchronously"""
        processor = batch_check.LLMProcessor(
            output_path=output_path,
            system_message=self.system_message,
            session_name=session_name,
            output_fields=self.fields,
        )

        # Run screening
        processor.run(documents, batch_size=25, sleep_time=0.5)
