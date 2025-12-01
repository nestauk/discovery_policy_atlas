from __future__ import annotations

import logging
import uuid
import shutil
from pathlib import Path
from typing import Dict, List
import pandas as pd
from datetime import datetime

from .schemas import RunConfig, RunResult
from .references import ReferencesService
from .relevance import RelevanceService
from .acquire import AcquisitionService
from .parse import ParsingService
from .normalize import normalize_text
from .extractor_langchain import LangChainExtractorService, LangChainExtractionConfig
from .storage import AnalysisStorageService
from app.core.config import settings
from app.services.monitoring import ResourceMonitor, StageTimer


logger = logging.getLogger(__name__)


class AnalysisService:
    """High-level orchestrator for the deterministic analysis pipeline.

    Pipeline steps:
    1. References ingestion and normalization
    1.5. Relevance checking and document type classification
    2. Acquisition (download PDFs/HTML) - filtered to relevant documents only
    3. Parsing and normalization
    4. Extraction using LangChain workflow

    Additional steps (postprocess, rag build) will be added incrementally.
    """

    def __init__(self, export_dir: str):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        config: RunConfig,
        project_id: str = None,
        user_id: str = None,
        user_name: str = None,
    ) -> RunResult:
        # Generate run ID with timestamp for better identification (max 12 chars for DB compatibility)
        timestamp = datetime.now().strftime("%m%d%H%M")  # MMDDHHMM = 8 chars
        uuid_part = uuid.uuid4().hex[:4]  # 4 chars
        run_id = f"{timestamp}{uuid_part}"  # Total: 12 chars
        logger.info("Starting analysis run %s", run_id)

        # Initialize resource monitoring
        monitor = ResourceMonitor(f"AnalysisService-{run_id}")
        monitor.start()
        monitor.log_snapshot("Pipeline start")

        # Create unique subfolder for this run
        run_export_dir = self.export_dir / f"run_{run_id}"
        run_export_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created run directory: %s", run_export_dir)

        # Step 1: build references
        with StageTimer(monitor, "references"):
            references_service = ReferencesService(export_dir=str(run_export_dir))
            # Convert search_context to dict if it's a Pydantic model
            search_context_dict = None
            if config.search_context:
                if hasattr(config.search_context, "dict"):
                    search_context_dict = config.search_context.dict()
                else:
                    search_context_dict = config.search_context

            (
                references_csv,
                generated_boolean_query,
                generated_semantic_query,
            ) = await references_service.build_references(
                query=config.query,
                sources=config.sources,
                limit=config.limit,
                date_from=config.date_from,
                date_to=config.date_to,
                mode=config.retrieval_mode,
                boolean_query=config.boolean_query,
                geography_filter=config.geography_filter,
                project_id=project_id,
                user_id=user_id,
                search_context=search_context_dict,
            )

        # Count rows
        try:
            import pandas as pd

            df = pd.read_csv(references_csv)
            total_references = len(df)
        except Exception:
            total_references = 0

        monitor.record_metric("total_references", total_references)
        logger.info(
            "Run %s completed references stage with %d items", run_id, total_references
        )

        # Step 1.5: relevance checking (NEW)
        relevant_references = 0
        if config.relevance_enabled:
            with StageTimer(monitor, "relevance"):
                logger.info("Run %s starting relevance checking", run_id)
                relevance_service = RelevanceService(
                    query=config.query,
                    export_dir=str(run_export_dir),
                    project_id=project_id,
                    user_id=user_id,
                )
                references_csv = await relevance_service.check_relevance(
                    str(references_csv)
                )

                # Add acquisition tracking columns to references CSV
                references_csv = relevance_service.add_acquisition_tracking_columns(
                    str(references_csv)
                )

                # Count relevant documents for reporting
                try:
                    df = pd.read_csv(references_csv)
                    relevant_references = (
                        df["is_relevant"].sum()
                        if "is_relevant" in df.columns
                        else total_references
                    )
                except Exception:
                    relevant_references = total_references

            monitor.record_metric("relevant_references", relevant_references)
            logger.info(
                "Run %s completed relevance checking: %d relevant out of %d total",
                run_id,
                relevant_references,
                total_references,
            )

            # STEPWISE UPLOAD: Store initial documents after screening
            if project_id:
                await self._store_initial_documents(project_id, references_csv)

        else:
            relevant_references = total_references
            logger.info("Run %s skipping relevance checking (disabled)", run_id)

            # STEPWISE UPLOAD: Store initial documents even without relevance checking
            if project_id:
                await self._store_initial_documents(project_id, references_csv)

        parsed_dir = run_export_dir / "data" / "normalized"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        acquired = []

        if not config.use_abstracts_only:
            # Step 2: acquisition (download PDFs/HTML) - only for relevant documents
            with StageTimer(monitor, "acquisition"):
                acquisition = AcquisitionService(export_dir=str(run_export_dir))
                acquired = await acquisition.acquire_all(references_csv)
                monitor.record_metric("acquired_count", len(acquired))

            # Step 3: parsing and normalization
            with StageTimer(monitor, "parsing"):
                parser = ParsingService(export_dir=str(run_export_dir))
                parsed_count = 0

                for item in acquired:
                    if not item or item.get("status") != "ok":
                        continue
                    # Use async parsing with guardrails
                    parsed = await parser.parse_saved_file(
                        item["doc_id"], item["file_path"]
                    )
                    if not parsed or not parsed.text:
                        continue
                    parsed_count += 1
                    norm_text = normalize_text(parsed.text)
                    # Use sanitized filename for normalized output as well
                    from .utils_paths import sanitize_id_to_filename

                    # Match normalized filename to raw base name
                    raw_path = (
                        Path(item["file_path"]) if item.get("file_path") else None
                    )
                    if raw_path is not None:
                        base = raw_path.stem  # without extension
                    else:
                        base = sanitize_id_to_filename(item["doc_id"])
                    safe_name = f"{base}.txt"
                    out_path = parsed_dir / safe_name
                    out_path.write_text(norm_text, encoding="utf-8")

                monitor.record_metric("parsed_count", parsed_count)

        # Step 4: extraction using LangChain workflow
        with StageTimer(monitor, "extraction"):
            extractor = LangChainExtractorService(
                LangChainExtractionConfig(
                    run_id=run_id,
                    export_dir=str(run_export_dir),
                    use_abstracts_only=config.use_abstracts_only,
                    model=settings.LLM_MODEL,
                    temperature=0.0,
                    concurrency=settings.BATCH_SIZE_EXTRACTION,
                    project_id=project_id,
                    user_id=user_id,
                )
            )

            # Update references CSV with acquisition status first
            if acquired:
                self._update_acquisition_status(str(references_csv), acquired)

            # Run extraction and get consolidated JSON path
            consolidated_json_path = await extractor.extract_for_documents(
                references_csv=str(references_csv),
                normalized_dir=str(parsed_dir),
            )

        # Consolidated outputs are now available:
        # - references.csv: Single file with all reference data, relevance, acquisition, and extraction status
        # - extractions.json: Single file with all extraction results

        result = RunResult(
            run_id=run_id,
            total_references=total_references,
            relevant_references=relevant_references,
            references_csv_path=str(references_csv),
            extractions_json_path=consolidated_json_path,
            boolean_query=generated_boolean_query,
            semantic_query=generated_semantic_query,
        )

        # Store results in Supabase and optionally clean up files
        try:
            with StageTimer(monitor, "storage"):
                logger.info("Starting Supabase upload for run %s", run_id)
                storage_service = AnalysisStorageService()
                storage_project_id = await storage_service.store_analysis_run(
                    config, result, project_id, user_id, user_name
                )
                logger.info(
                    "Successfully stored analysis run %s to project %s",
                    run_id,
                    storage_project_id or project_id,
                )

            # Clean up local files unless in debug mode
            if not settings.DEBUG_ANALYSIS_FILES:
                logger.info("Cleaning up local files for run %s", run_id)
                self._cleanup_run_files(run_export_dir)
            else:
                logger.info(
                    "Debug mode enabled - keeping local files for run %s", run_id
                )

        except Exception as e:
            logger.error("Failed to store analysis run %s in Supabase: %s", run_id, e)
            # Don't fail the entire pipeline if Supabase upload fails
            # Keep the files for manual inspection

        # Log final monitoring summary
        monitor.log_snapshot("Pipeline complete")
        monitor.log_summary()

        return result

    def _update_acquisition_status(
        self, references_csv_path: str, acquisition_results: List[Dict]
    ) -> None:
        """Update references CSV with acquisition status and results."""
        try:
            df = pd.read_csv(references_csv_path)

            # Create mapping of doc_id to acquisition results
            acquisition_mapping = {}
            for result in acquisition_results:
                if not result:
                    continue

                doc_id = result.get("doc_id")
                status = result.get("status", "failed")

                if status == "ok":
                    acquisition_mapping[doc_id] = {
                        "acquisition_status": "success",
                        "acquisition_error": None,
                        "full_text_available": True,
                        "file_path": result.get("file_path"),
                    }
                else:
                    acquisition_mapping[doc_id] = {
                        "acquisition_status": "failed",
                        "acquisition_error": result.get(
                            "error", "Unknown acquisition error"
                        ),
                        "full_text_available": False,
                        "file_path": None,
                    }

            # Update DataFrame with acquisition results
            for idx, row in df.iterrows():
                doc_id = row.get("doc_id")
                is_relevant = row.get("is_relevant", False)

                if doc_id in acquisition_mapping:
                    # Document was processed by acquisition
                    acquisition_info = acquisition_mapping[doc_id]
                    for field, value in acquisition_info.items():
                        df.at[idx, field] = value
                elif is_relevant:
                    # Relevant document but not in acquisition results (unexpected)
                    df.at[idx, "acquisition_status"] = "failed"
                    df.at[
                        idx, "acquisition_error"
                    ] = "Document not found in acquisition results"
                    df.at[idx, "full_text_available"] = False
                    df.at[idx, "file_path"] = None
                else:
                    # Non-relevant document - not attempted
                    df.at[idx, "acquisition_status"] = "not_attempted"
                    df.at[idx, "acquisition_error"] = "Document not relevant"
                    df.at[idx, "full_text_available"] = False
                    df.at[idx, "file_path"] = None

            # Save updated CSV
            df.to_csv(references_csv_path, index=False)
            logger.info(
                f"Updated references CSV with acquisition status: {references_csv_path}"
            )

        except Exception as e:
            logger.error(f"Failed to update acquisition status: {e}")

    def _cleanup_run_files(self, run_export_dir: Path) -> None:
        """Clean up local files for a run after successful Supabase upload."""
        try:
            if run_export_dir.exists() and run_export_dir.is_dir():
                shutil.rmtree(run_export_dir)
                logger.info(f"Cleaned up run directory: {run_export_dir}")
            else:
                logger.warning(f"Run directory not found for cleanup: {run_export_dir}")
        except Exception as e:
            logger.error(f"Failed to clean up run directory {run_export_dir}: {e}")
            # Don't raise - cleanup failure shouldn't fail the pipeline

    async def _store_initial_documents(
        self, project_id: str, references_csv: str
    ) -> None:
        """Store initial documents after screening phase."""
        try:
            logger.info(f"Storing initial documents for project {project_id}")

            # Load CSV and convert to UnifiedReference objects
            references = self._load_references_from_csv(references_csv)

            # Store using the enhanced storage service
            storage_service = AnalysisStorageService()
            await storage_service.store_initial_documents(project_id, references)

            logger.info(f"Successfully stored {len(references)} initial documents")

        except Exception as e:
            logger.error(f"Failed to store initial documents: {e}")
            # Don't raise - this shouldn't stop the analysis pipeline

    def _load_references_from_csv(self, csv_path: str) -> List:
        """Load references from CSV and convert to UnifiedReference objects."""
        from .schemas import UnifiedReference

        df = pd.read_csv(csv_path)

        references = []

        logger.info(
            f"Loading {len(df)} references from CSV with {len(df.columns)} columns"
        )

        for _, row in df.iterrows():
            # Map CSV columns to UnifiedReference fields
            ref_data = {
                "doc_id": str(row.get("doc_id", "")),
                "source": str(row.get("source", "")),
                "source_id": str(row.get("source_id", "")),
                "title": str(row.get("title", "")),
                "abstract_or_summary": self._safe_str(row.get("abstract_or_summary")),
                "year": self._safe_int(row.get("year")),
                "doi": self._safe_str(row.get("doi")),
                "authors": self._parse_authors(row.get("authors")),
                "landing_page_url": self._safe_str(row.get("landing_page_url")),
                "pdf_url": self._safe_str(row.get("pdf_url")),
                "is_oa": self._safe_bool(row.get("is_oa")),
                "type": self._safe_str(row.get("type")),
                "author_institution_countries": self._parse_list(
                    row.get("author_institution_countries")
                ),
                # Relevance fields
                "is_relevant": self._safe_bool(row.get("is_relevant")),
                "relevance_confidence": self._safe_float(
                    row.get("relevance_confidence")
                ),
                "relevance_reason": self._safe_str(row.get("relevance_reason")),
                "top_line": self._safe_str(row.get("top_line")),
                "document_type": self._safe_str(row.get("document_type")),
                "document_type_reason": self._safe_str(row.get("document_type_reason")),
                # Essential fields: citation count and source country
                "cited_by_count": self._safe_int(row.get("cited_by_count")),
                "source_country": self._safe_str(row.get("source_country")),
                # Acquisition fields
                "acquisition_status": self._safe_str(row.get("acquisition_status")),
                "acquisition_error": self._safe_str(row.get("acquisition_error")),
                "full_text_available": self._safe_bool(row.get("full_text_available")),
                "file_path": self._safe_str(row.get("file_path")),
                # Extraction fields
                "extraction_status": self._safe_str(row.get("extraction_status")),
                "extraction_error": self._safe_str(row.get("extraction_error")),
                "text_source": self._safe_str(row.get("text_source")),
            }

            # Create UnifiedReference object
            try:
                ref = UnifiedReference(**ref_data)
                references.append(ref)

            except Exception as e:
                logger.warning(
                    f"Failed to create UnifiedReference for doc {ref_data.get('doc_id')}: {e}"
                )
                logger.warning(f"ref_data was: {ref_data}")
                continue

        return references

    def _safe_str(self, value) -> str | None:
        """Safely convert value to string, handling NaN/None."""
        if pd.isna(value) or value is None or value == "":
            return None
        return str(value).strip()

    def _safe_int(self, value) -> int | None:
        """Safely convert value to int, handling NaN/None."""
        if pd.isna(value) or value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value) -> float | None:
        """Safely convert value to float, handling NaN/None."""
        if pd.isna(value) or value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_bool(self, value) -> bool | None:
        """Safely convert value to bool, handling NaN/None."""
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return None

    def _parse_authors(self, value) -> List[str] | None:
        """Parse authors field which might be a string or list."""
        if pd.isna(value) or value is None or value == "":
            return None

        if isinstance(value, list):
            return [str(author) for author in value]

        # Try JSON parsing for list-like strings first
        try:
            import json

            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                return [str(author) for author in parsed]
            elif isinstance(parsed, str):
                return [parsed]
        except (json.JSONDecodeError, ValueError):
            pass

        # Try literal_eval for Python list representations like "['Author Name']"
        try:
            import ast

            parsed = ast.literal_eval(str(value))
            if isinstance(parsed, list):
                return [str(author) for author in parsed]
            elif isinstance(parsed, str):
                return [parsed]
        except (ValueError, SyntaxError):
            pass

        # Fallback to comma separation
        return [author.strip() for author in str(value).split(",") if author.strip()]

    def _parse_list(self, value) -> List[str] | None:
        """Parse a generic list field."""
        if pd.isna(value) or value is None or value == "":
            return None

        if isinstance(value, list):
            return [str(item) for item in value]

        try:
            import json

            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, ValueError):
            pass

        return [item.strip() for item in str(value).split(",") if item.strip()]
