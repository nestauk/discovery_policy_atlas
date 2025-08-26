from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Dict, List
import pandas as pd

from .schemas import RunConfig, RunResult
from .references import ReferencesService
from .relevance import RelevanceService
from .acquire import AcquisitionService
from .parse import ParsingService
from .normalize import normalize_text
from .extractor_langchain import LangChainExtractorService, LangChainExtractionConfig
from app.core.config import settings


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

    async def run(self, config: RunConfig) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        logger.info("Starting analysis run %s", run_id)

        # Create unique subfolder for this run
        run_export_dir = self.export_dir / f"run_{run_id}"
        run_export_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created run directory: %s", run_export_dir)

        # Step 1: build references
        references_service = ReferencesService(export_dir=str(run_export_dir))
        references_csv = await references_service.build_references(
            query=config.query,
            sources=config.sources,
            limit=config.limit,
            date_from=config.date_from,
            date_to=config.date_to,
            mode=config.retrieval_mode,
            boolean_query=config.boolean_query,
        )

        # Count rows
        try:
            import pandas as pd

            df = pd.read_csv(references_csv)
            total_references = len(df)
        except Exception:
            total_references = 0

        logger.info(
            "Run %s completed references stage with %d items", run_id, total_references
        )

        # Step 1.5: relevance checking (NEW)
        relevant_references = 0
        if config.relevance_enabled:
            logger.info("Run %s starting relevance checking", run_id)
            relevance_service = RelevanceService(
                query=config.query, export_dir=str(run_export_dir)
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

            logger.info(
                "Run %s completed relevance checking: %d relevant out of %d total",
                run_id,
                relevant_references,
                total_references,
            )
        else:
            relevant_references = total_references
            logger.info("Run %s skipping relevance checking (disabled)", run_id)

        parsed_dir = run_export_dir / "data" / "normalized"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        acquired = []

        if not config.use_abstracts_only:
            # Step 2: acquisition (download PDFs/HTML) - only for relevant documents
            acquisition = AcquisitionService(export_dir=str(run_export_dir))
            acquired = await acquisition.acquire_all(references_csv)

            # Step 3: parsing and normalization
            parser = ParsingService(export_dir=str(run_export_dir))

            for item in acquired:
                if not item or item.get("status") != "ok":
                    continue
                parsed = parser.parse_saved_file(item["doc_id"], item["file_path"])
                if not parsed or not parsed.text:
                    continue
                norm_text = normalize_text(parsed.text)
                # Use sanitized filename for normalized output as well
                from .utils_paths import sanitize_id_to_filename

                # Match normalized filename to raw base name
                raw_path = Path(item["file_path"]) if item.get("file_path") else None
                if raw_path is not None:
                    base = raw_path.stem  # without extension
                else:
                    base = sanitize_id_to_filename(item["doc_id"])
                safe_name = f"{base}.txt"
                out_path = parsed_dir / safe_name
                out_path.write_text(norm_text, encoding="utf-8")

        # Step 4: extraction using LangChain workflow
        extractor = LangChainExtractorService(
            LangChainExtractionConfig(
                run_id=run_id,
                export_dir=str(run_export_dir),
                use_abstracts_only=config.use_abstracts_only,
                model=settings.LLM_MODEL,
                temperature=0.0,
                concurrency=settings.BATCH_SIZE_EXTRACTION,
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

        return RunResult(
            run_id=run_id,
            total_references=total_references,
            relevant_references=relevant_references,
            references_csv_path=str(references_csv),
            extractions_json_path=consolidated_json_path,
        )

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
