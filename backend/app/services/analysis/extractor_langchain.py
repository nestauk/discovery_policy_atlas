"""
LangChain/LangGraph-based document extraction service.
Replaces the old OpenAI-based extractor with a more structured workflow.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import settings
from .workflow_langchain import ExtractionWorkflow

logger = logging.getLogger(__name__)


@dataclass
class LangChainExtractionConfig:
    """Configuration for the LangChain-based extraction service."""

    run_id: str
    export_dir: str
    use_abstracts_only: bool = False
    model: str = settings.LLM_MODEL
    temperature: float = 0.0
    concurrency: int = 3


class LangChainExtractorService:
    """LangChain/LangGraph-based document extraction service."""

    def __init__(self, config: LangChainExtractionConfig):
        self.config = config
        self.export_dir = Path(config.export_dir)
        self.workflow = ExtractionWorkflow(
            model=config.model,
            temperature=config.temperature,
        )
        # No need to create extractions directory - we'll create consolidated JSON directly

    async def extract_for_documents(
        self, references_csv: str, normalized_dir: str
    ) -> str:
        """Extract structured data from all documents and create consolidated JSON."""
        df = pd.read_csv(references_csv)

        # Filter to only relevant documents if relevance checking was performed
        if "is_relevant" in df.columns:
            relevant_df = df[df["is_relevant"]].copy()
            skipped_count = len(df) - len(relevant_df)
            logger.info(
                f"Extraction filtering: processing {len(relevant_df)} relevant documents, "
                f"skipping {skipped_count} irrelevant documents"
            )
            df = relevant_df
        else:
            logger.info("No relevance filtering available - processing all documents")

        warnings: List[Dict[str, Any]] = []
        all_extractions: List[Dict[str, Any]] = []

        async def _process_row(row: pd.Series) -> Optional[Dict[str, Any]]:
            """Process a single document row."""
            doc_id = row["doc_id"]

            print(f"\n📄 Processing: {doc_id}")

            # Find corresponding normalized text file
            norm_path = self._find_normalized_path(normalized_dir, doc_id)
            if norm_path is None or not Path(norm_path).exists():
                # Fall back to abstract if allowed
                text = (row.get("abstract_or_summary") or "").strip()
                if not text:
                    print(f"❌ No text found for {doc_id}")
                    return None
                doc_text = text
                short_text_only = True
                print(f"📝 Using abstract ({len(doc_text)} chars)")
            else:
                doc_text = Path(norm_path).read_text(encoding="utf-8", errors="ignore")
                short_text_only = False
                print(f"📄 Using full text ({len(doc_text)} chars)")

            # Abstracts-only mode override
            if self.config.use_abstracts_only and row.get("abstract_or_summary"):
                doc_text = str(row.get("abstract_or_summary"))
                short_text_only = True
                print(f"📝 Forced abstract-only mode ({len(doc_text)} chars)")

            # Skip processing if text is too short and likely incomplete
            if len(doc_text) < 500:
                warnings.append(
                    {
                        "doc_id": doc_id,
                        "reason": "text_too_short",
                        "text_length": len(doc_text),
                    }
                )
                print(f"⚠️  Skipping extraction (text too short: {len(doc_text)} chars)")
                return None

            # Run the LangGraph workflow
            try:
                extraction = await self.workflow.run(doc_id, doc_text)

                print("📊 Extraction results:")
                print(f"  • Issues: {len(extraction.issues)}")
                print(f"  • Interventions: {len(extraction.interventions)}")
                print(f"  • Mappings: {len(extraction.mappings)}")
                print(f"  • Results: {len(extraction.results)}")
                print(f"  • Conclusion: {'1' if extraction.conclusion else '0'}")

                # Add extraction to our list (no individual files)
                # Add metadata and add to extractions list
                extraction_data = extraction.model_dump()
                extraction_data["extraction_metadata"] = {
                    "text_length": len(doc_text),
                    "text_source": "abstract" if short_text_only else "full_text",
                    "processed_at": datetime.now().isoformat(),
                    "file_size_bytes": len(json.dumps(extraction_data).encode("utf-8")),
                }
                all_extractions.append(extraction_data)

                # Show final result status
                total_items = (
                    len(extraction.issues)
                    + len(extraction.interventions)
                    + len(extraction.mappings)
                    + len(extraction.results)
                    + (1 if extraction.conclusion else 0)
                )
                if total_items == 0:
                    print(f"⚠️  EMPTY EXTRACTION for {doc_id}")
                    warnings.append(
                        {
                            "doc_id": doc_id,
                            "reason": "empty_extraction",
                        }
                    )
                else:
                    print(
                        f"✅ Extraction completed for {doc_id} ({total_items} total items)"
                    )

                return extraction_data

            except Exception as e:
                logger.error(f"Extraction failed for {doc_id}: {e}")
                warnings.append(
                    {
                        "doc_id": doc_id,
                        "reason": "extraction_failed",
                        "error": str(e),
                    }
                )
                print(f"❌ Extraction failed: {e}")
                return None

        # Process documents with concurrency control
        sem = asyncio.Semaphore(self.config.concurrency)

        async def _guarded(row: pd.Series) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    return await _process_row(row)
                except Exception as e:
                    logger.error("Extraction failed for %s: %s", row.get("doc_id"), e)
                    return None

        results = await asyncio.gather(*[_guarded(r) for _, r in df.iterrows()])

        # Filter successful results and add to all_extractions
        for result in results:
            if result is not None:
                all_extractions.append(result)

        print("\n📈 Batch extraction complete:")
        print(f"  • Total documents: {len(df)}")
        print(f"  • Successful extractions: {len(all_extractions)}")
        print(f"  • Failed/skipped: {len(df) - len(all_extractions)}")

        # Write warnings CSV
        if warnings:
            warnings_df = pd.DataFrame(warnings)
            warnings_df.to_csv(self.export_dir / "extraction_warnings.csv", index=False)
            print("  • Warnings written to extraction_warnings.csv")

        # Create consolidated JSON directly
        consolidated_json_path = self._create_consolidated_json(
            all_extractions, references_csv
        )

        # Update references CSV with extraction status
        self._update_references_with_extraction_status(
            references_csv, all_extractions, warnings
        )

        return consolidated_json_path

    def _create_consolidated_json(
        self, all_extractions: List[Dict[str, Any]], references_csv: str
    ) -> str:
        """Create single consolidated JSON file with all extractions."""
        # Create consolidated structure
        consolidated_data = {
            "run_metadata": {
                "run_id": self.config.run_id,
                "export_dir": self.config.export_dir,
                "use_abstracts_only": self.config.use_abstracts_only,
                "model": self.config.model,
                "concurrency": self.config.concurrency,
                "total_documents": self._count_total_documents(references_csv),
                "processed_documents": len(all_extractions),
                "created_at": datetime.now().isoformat(),
            },
            "extractions": all_extractions,
        }

        # Write consolidated JSON
        consolidated_path = self.export_dir / "extractions.json"
        with open(consolidated_path, "w") as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Created consolidated extractions file: {consolidated_path}")
        logger.info(f"Consolidated {len(all_extractions)} extractions")

        return str(consolidated_path)

    def _update_references_with_extraction_status(
        self,
        references_csv: str,
        all_extractions: List[Dict[str, Any]],
        warnings: List[Dict[str, Any]],
    ) -> None:
        """Update references CSV with extraction status and metadata."""
        try:
            df = pd.read_csv(references_csv)

            # Create mapping of doc_id to extraction status
            extraction_mapping = {}

            # Process successful extractions
            for extraction_data in all_extractions:
                doc_id = extraction_data.get("paper_id")
                if doc_id:
                    metadata = extraction_data.get("extraction_metadata", {})
                    extraction_mapping[doc_id] = {
                        "extraction_status": "success",
                        "extraction_error": None,
                        "text_source": metadata.get("text_source", "unknown"),
                    }

            # Process warnings/failures
            for warning in warnings:
                doc_id = warning.get("doc_id")
                if doc_id and doc_id not in extraction_mapping:
                    extraction_mapping[doc_id] = {
                        "extraction_status": "failed",
                        "extraction_error": warning.get("reason", "Unknown error"),
                        "text_source": None,
                    }

            # Update references DataFrame
            for idx, row in df.iterrows():
                doc_id = row.get("doc_id")
                if doc_id in extraction_mapping:
                    extraction_info = extraction_mapping[doc_id]
                    for field, value in extraction_info.items():
                        df.at[idx, field] = value
                else:
                    # Document not processed (likely not relevant or skipped)
                    df.at[idx, "extraction_status"] = "skipped"
                    df.at[idx, "extraction_error"] = None
                    df.at[idx, "text_source"] = None

            # Save updated references CSV
            df.to_csv(references_csv, index=False)
            logger.info(
                f"Updated references CSV with extraction metadata: {references_csv}"
            )

        except Exception as e:
            logger.error(f"Failed to update references with extraction data: {e}")

    def write_consolidated_json(self, extractions_dir: str, references_csv: str) -> str:
        """Create single consolidated JSON file with all extractions."""
        extractions_path = Path(extractions_dir)
        json_files = list(extractions_path.glob("*.json"))

        # Read all individual extraction files
        all_extractions = []
        for json_file in json_files:
            try:
                with open(json_file, "r") as f:
                    extraction_data = json.load(f)

                # Add metadata about the extraction
                extraction_data["extraction_metadata"] = {
                    "file_name": json_file.name,
                    "file_size_bytes": json_file.stat().st_size,
                    "processed_at": datetime.now().isoformat(),
                }

                all_extractions.append(extraction_data)

            except Exception as e:
                logger.error(f"Failed to read extraction file {json_file}: {e}")
                continue

        # Create consolidated structure
        consolidated_data = {
            "run_metadata": {
                "run_id": self.config.run_id,
                "export_dir": self.config.export_dir,
                "use_abstracts_only": self.config.use_abstracts_only,
                "model": self.config.model,
                "concurrency": self.config.concurrency,
                "total_documents": self._count_total_documents(references_csv),
                "processed_documents": len(all_extractions),
                "created_at": datetime.now().isoformat(),
            },
            "extractions": all_extractions,
        }

        # Write consolidated JSON
        consolidated_path = self.export_dir / "extractions.json"
        with open(consolidated_path, "w") as f:
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Created consolidated extractions file: {consolidated_path}")
        logger.info(f"Consolidated {len(all_extractions)} extractions")

        return str(consolidated_path)

    def update_references_with_extraction_status(
        self, references_csv: str, extractions_dir: str
    ) -> str:
        """Update references CSV with extraction status and metadata."""
        try:
            df = pd.read_csv(references_csv)
            extractions_path = Path(extractions_dir)

            # Create mapping of doc_id to extraction status
            extraction_mapping = {}

            # Process successful extractions
            json_files = list(extractions_path.glob("*.json"))
            for json_file in json_files:
                try:
                    with open(json_file, "r") as f:
                        extraction_data = json.load(f)
                        doc_id = extraction_data.get("paper_id")

                        if doc_id:
                            # Determine text source from the extraction data
                            text_source = "abstract"  # default
                            if "text_metadata" in extraction_data:
                                text_length = extraction_data["text_metadata"].get(
                                    "text_length", 0
                                )
                                # Heuristic: if text is long, likely full text
                                text_source = (
                                    "full_text" if text_length > 5000 else "abstract"
                                )

                            extraction_mapping[doc_id] = {
                                "extraction_status": "success",
                                "extraction_error": None,
                                "text_source": text_source,
                            }
                except Exception as e:
                    logger.warning(
                        f"Failed to process extraction file {json_file}: {e}"
                    )
                    continue

            # Process extraction warnings/failures
            warnings_file = extractions_path / "extraction_warnings.csv"
            if warnings_file.exists():
                try:
                    warnings_df = pd.read_csv(warnings_file)
                    for _, warning_row in warnings_df.iterrows():
                        doc_id = warning_row.get("doc_id")
                        if doc_id and doc_id not in extraction_mapping:
                            extraction_mapping[doc_id] = {
                                "extraction_status": "failed",
                                "extraction_error": warning_row.get(
                                    "warning", "Unknown error"
                                ),
                                "text_source": None,
                            }
                except Exception as e:
                    logger.warning(f"Failed to process extraction warnings: {e}")

            # Update references DataFrame
            for idx, row in df.iterrows():
                doc_id = row.get("doc_id")
                if doc_id in extraction_mapping:
                    extraction_info = extraction_mapping[doc_id]
                    for field, value in extraction_info.items():
                        df.at[idx, field] = value
                else:
                    # Document not processed (likely not relevant or skipped)
                    df.at[idx, "extraction_status"] = "skipped"
                    df.at[idx, "extraction_error"] = None
                    df.at[idx, "text_source"] = None

            # Save updated references CSV
            df.to_csv(references_csv, index=False)
            logger.info(
                f"Updated references CSV with extraction metadata: {references_csv}"
            )

            return references_csv

        except Exception as e:
            logger.error(f"Failed to update references with extraction data: {e}")
            return references_csv

    def _count_total_documents(self, references_csv: str) -> int:
        """Count total documents in references CSV."""
        try:
            df = pd.read_csv(references_csv)
            return len(df)
        except Exception:
            return 0

    def write_csvs(self, references_csv: str, extractions_dir: str) -> Dict[str, str]:
        """Convert JSON extractions to tidy CSV format."""
        in_dir = Path(extractions_dir)
        issues_rows: List[Dict[str, Any]] = []
        interventions_rows: List[Dict[str, Any]] = []
        mappings_rows: List[Dict[str, Any]] = []
        results_rows: List[Dict[str, Any]] = []
        conclusions_rows: List[Dict[str, Any]] = []

        # Load reference metadata
        ref_df = pd.read_csv(references_csv)
        meta = ref_df.set_index("doc_id").to_dict("index")

        # Process each extraction file
        for path in in_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                doc_id = data.get(
                    "paper_id"
                )  # Note: using paper_id from the new schema
                m = meta.get(doc_id, {})
                run_id = self.config.run_id

                # Issues
                for item in data.get("issues", []):
                    row = {
                        "doc_id": doc_id,
                        "idx": item.get("idx"),
                        "label": item.get("label"),
                        "explanation": item.get("explanation"),
                        "supporting_quote": item.get("supporting_quote"),
                        "source": m.get("source"),
                        "year": m.get("year"),
                        "run_id": run_id,
                    }
                    issues_rows.append(row)

                # Interventions
                for item in data.get("interventions", []):
                    row = {
                        "doc_id": doc_id,
                        "idx": item.get("idx"),
                        "name": item.get("name"),
                        "type": item.get("type"),
                        "description": item.get("description"),
                        "study_type": item.get("study_type"),
                        "country": item.get("country"),
                        "population_intervened": item.get("population_intervened"),
                        "population_demographics": item.get("population_demographics"),
                        "sample_size": item.get("sample_size"),
                        "supporting_quote": item.get("supporting_quote"),
                        "source": m.get("source"),
                        "year": m.get("year"),
                        "run_id": run_id,
                    }
                    interventions_rows.append(row)

                # Mappings
                for item in data.get("mappings", []):
                    row = {
                        "doc_id": doc_id,
                        "issue_idx": item.get("issue_idx"),
                        "intervention_idx": item.get("intervention_idx"),
                        "rationale": item.get("rationale"),
                        "supporting_quote": item.get("supporting_quote"),
                        "source": m.get("source"),
                        "year": m.get("year"),
                        "run_id": run_id,
                    }
                    mappings_rows.append(row)

                # Results
                for item in data.get("results", []):
                    row = {
                        "doc_id": doc_id,
                        "intervention_idx": item.get("intervention_idx"),
                        "outcome_variable": item.get("outcome_variable"),
                        "effect_direction": item.get("effect_direction"),
                        "effect_size_type": item.get("effect_size_type"),
                        "effect_size": item.get("effect_size"),
                        "uncertainty": item.get("uncertainty"),
                        "p_value": item.get("p_value"),
                        "population_measured": item.get("population_measured"),
                        "subgroup_or_dose": item.get("subgroup_or_dose"),
                        "result_text": item.get("result_text"),
                        "supporting_quote": item.get("supporting_quote"),
                        "source": m.get("source"),
                        "year": m.get("year"),
                        "run_id": run_id,
                    }
                    results_rows.append(row)

                # Conclusions
                conclusion = data.get("conclusion")
                if conclusion:
                    row = {
                        "doc_id": doc_id,
                        "top_line_summary": conclusion.get("top_line_summary"),
                        "detailed_explanation": conclusion.get("detailed_explanation"),
                        "supporting_quote": conclusion.get("supporting_quote"),
                        "source": m.get("source"),
                        "year": m.get("year"),
                        "run_id": run_id,
                    }
                    conclusions_rows.append(row)

            except Exception as e:
                logger.error(f"Failed to process extraction file {path}: {e}")
                continue

        # Write CSV files to export directory
        out_csv_dir = self.export_dir

        issues_csv = out_csv_dir / "issues.csv"
        interventions_csv = out_csv_dir / "interventions.csv"
        mappings_csv = out_csv_dir / "mappings.csv"
        results_csv = out_csv_dir / "results.csv"
        conclusions_csv = out_csv_dir / "conclusions.csv"

        # Issues CSV
        if issues_rows:
            pd.DataFrame(issues_rows).to_csv(issues_csv, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "doc_id",
                    "idx",
                    "label",
                    "explanation",
                    "supporting_quote",
                    "source",
                    "year",
                    "run_id",
                ]
            ).to_csv(issues_csv, index=False)

        # Interventions CSV
        if interventions_rows:
            pd.DataFrame(interventions_rows).to_csv(interventions_csv, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "doc_id",
                    "idx",
                    "name",
                    "type",
                    "description",
                    "study_type",
                    "country",
                    "population_intervened",
                    "population_demographics",
                    "sample_size",
                    "supporting_quote",
                    "source",
                    "year",
                    "run_id",
                ]
            ).to_csv(interventions_csv, index=False)

        # Mappings CSV
        if mappings_rows:
            pd.DataFrame(mappings_rows).to_csv(mappings_csv, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "doc_id",
                    "issue_idx",
                    "intervention_idx",
                    "rationale",
                    "supporting_quote",
                    "source",
                    "year",
                    "run_id",
                ]
            ).to_csv(mappings_csv, index=False)

        # Results CSV
        if results_rows:
            pd.DataFrame(results_rows).to_csv(results_csv, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "doc_id",
                    "intervention_idx",
                    "outcome_variable",
                    "effect_direction",
                    "effect_size_type",
                    "effect_size",
                    "uncertainty",
                    "p_value",
                    "population_measured",
                    "subgroup_or_dose",
                    "result_text",
                    "supporting_quote",
                    "source",
                    "year",
                    "run_id",
                ]
            ).to_csv(results_csv, index=False)

        # Conclusions CSV
        if conclusions_rows:
            pd.DataFrame(conclusions_rows).to_csv(conclusions_csv, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "doc_id",
                    "top_line_summary",
                    "detailed_explanation",
                    "supporting_quote",
                    "source",
                    "year",
                    "run_id",
                ]
            ).to_csv(conclusions_csv, index=False)

        print("\n📊 CSV files written:")
        print(f"  • Issues: {len(issues_rows)} rows → {issues_csv}")
        print(
            f"  • Interventions: {len(interventions_rows)} rows → {interventions_csv}"
        )
        print(f"  • Mappings: {len(mappings_rows)} rows → {mappings_csv}")
        print(f"  • Results: {len(results_rows)} rows → {results_csv}")
        print(f"  • Conclusions: {len(conclusions_rows)} rows → {conclusions_csv}")

        return {
            "issues": str(issues_csv),
            "interventions": str(interventions_csv),
            "mappings": str(mappings_csv),
            "results": str(results_csv),
            "conclusions": str(conclusions_csv),
        }

    def load_extractions_as_dict(self, extractions_dir: str) -> Dict[str, Any]:
        """Load all extraction JSON files as a dictionary for programmatic access."""
        in_dir = Path(extractions_dir)
        extractions = {}

        for path in in_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                doc_id = data.get("paper_id")
                if doc_id:
                    extractions[doc_id] = data
            except Exception as e:
                logger.error(f"Failed to load extraction file {path}: {e}")
                continue

        return extractions

    def _find_normalized_path(self, normalized_dir: str, doc_id: str) -> Optional[str]:
        """Find the normalized text file for a document ID."""
        ndir = Path(normalized_dir)
        if not ndir.exists():
            return None

        candidates = list(ndir.glob("*.txt"))

        # Debug: show what we're trying to match
        print(f"🔍 Looking for normalized file for doc_id: {doc_id}")
        print(f"🔍 Available files: {[p.name for p in candidates]}")

        # Try exact match first
        for p in candidates:
            if doc_id in p.stem:
                print(f"✅ Found exact match: {p.name}")
                return str(p)

        # Try without protocol prefix (https://, http://)
        clean_doc_id = doc_id.replace("https://", "").replace("http://", "")
        for p in candidates:
            if clean_doc_id in p.stem:
                print(f"✅ Found match without protocol: {p.name}")
                return str(p)

        # Try with character normalization (/ -> _)
        normalized_doc_id = clean_doc_id.replace("/", "_")
        for p in candidates:
            if normalized_doc_id in p.stem or p.stem in normalized_doc_id:
                print(f"✅ Found match with normalization: {p.name}")
                return str(p)

        # Try reverse: check if filename (without extension) is in doc_id
        for p in candidates:
            if p.stem in doc_id:
                print(f"✅ Found reverse match: {p.name}")
                return str(p)

        print(f"❌ No matching file found for {doc_id}")
        return None
