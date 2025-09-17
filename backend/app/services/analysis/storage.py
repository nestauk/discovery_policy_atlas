"""
Supabase storage service for Analysis Service results.
Uploads references and extraction results to new analysis tables.
"""

from __future__ import annotations

import json
import logging
import pandas as pd
import math
from pathlib import Path
from typing import Dict, List, Optional, Any
from supabase import create_client
from app.core.config import settings
from .schemas import RunConfig, RunResult, UnifiedReference
from .schemas_langchain import DocumentExtractionBundle
from .chunking import chunk_document_text
from ..vectorization import VectorizationService

logger = logging.getLogger(__name__)


class AnalysisStorageService:
    """Service for storing analysis results in Supabase."""

    def __init__(self):
        self._supabase = None
        self._vectorization_service = None

    @property
    def supabase(self):
        """Lazy initialization of Supabase client."""
        if self._supabase is None:
            if not settings.SUPABASE_URL:
                raise ValueError(
                    "SUPABASE_URL is required for analysis storage service"
                )
            if not settings.SUPABASE_KEY:
                raise ValueError(
                    "SUPABASE_KEY is required for analysis storage service"
                )

            self._supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return self._supabase

    @property
    def vectorization_service(self):
        """Lazy initialization of Vectorization service."""
        if self._vectorization_service is None:
            self._vectorization_service = VectorizationService()
        return self._vectorization_service

    def _clean_data_for_json(self, data: Any) -> Any:
        """Clean data to prevent JSON serialization issues (NaN, None, etc.)."""
        if pd.isna(data):
            return None
        if isinstance(data, float) and math.isnan(data):
            return None
        if isinstance(data, (list, tuple)):
            return [self._clean_data_for_json(item) for item in data]
        if isinstance(data, dict):
            return {k: self._clean_data_for_json(v) for k, v in data.items()}
        return data

    async def store_initial_documents(
        self, project_id: str, references: List[UnifiedReference]
    ) -> None:
        """
        Store initial document references after acquisition/screening.
        This is called early in the analysis process.

        Args:
            project_id: The analysis project ID
            references: List of UnifiedReference objects with initial data
        """
        logger.info(
            f"Storing {len(references)} initial documents for project {project_id}"
        )

        # Prepare documents data with all available fields
        documents_data = []
        for ref in references:
            doc_data = self._map_reference_to_document(
                ref, project_id, upload_step="screened"
            )
            documents_data.append(doc_data)

        # Use upsert to handle potential duplicates
        if documents_data:
            await self._upsert_documents(documents_data)
            logger.info(f"Successfully stored {len(documents_data)} initial documents")

    async def check_existing_extractions(self, project_id: str) -> Dict[str, bool]:
        """
        Check which documents already have extractions in the database.

        Args:
            project_id: The analysis project ID

        Returns:
            Dict mapping doc_id to boolean indicating if extraction exists
        """
        logger.info(f"Checking existing extractions for project {project_id}")

        try:
            # Query documents that have extraction_status = 'completed' or 'success'
            response = (
                self.supabase.table("analysis_documents")
                .select("doc_id,extraction_status")
                .eq("analysis_project_id", project_id)
                .in_("extraction_status", ["completed", "success"])
                .execute()
            )

            existing_extractions = {doc["doc_id"]: True for doc in response.data}

            logger.info(
                f"Found {len(existing_extractions)} documents with existing extractions"
            )
            return existing_extractions

        except Exception as e:
            logger.error(f"Failed to check existing extractions: {e}")
            return {}

    async def store_single_extraction(
        self, project_id: str, doc_id: str, extraction_data: Dict[str, Any]
    ) -> bool:
        """
        Store extraction results for a single document immediately.
        Updates both documents and extractions tables.

        Args:
            project_id: The analysis project ID
            doc_id: The document ID
            extraction_data: The extraction results

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(
                f"Storing extraction for document {doc_id} in project {project_id}"
            )

            # 1. Update the document with extraction results
            doc_update = {
                "extraction_results": extraction_data,
                "extraction_status": "completed",
                "upload_step": "extracted",
            }

            doc_response = (
                self.supabase.table("analysis_documents")
                .update(doc_update)
                .eq("analysis_project_id", project_id)
                .eq("doc_id", doc_id)
                .execute()
            )

            if not doc_response.data:
                logger.warning(
                    f"Failed to update document {doc_id} - not found in project {project_id}"
                )
                return False

            # 2. Get the document database ID for extractions table
            document_db_id = doc_response.data[0]["id"]

            # 3. Create extraction bundle and store individual items
            from .schemas_langchain import DocumentExtractionBundle

            bundle = DocumentExtractionBundle(**extraction_data)

            base_data = {
                "analysis_project_id": project_id,
                "analysis_document_id": document_db_id,
            }

            extraction_items = self._create_extraction_items(bundle, base_data)

            # 4. Insert extraction items (delete existing ones first to handle re-runs)
            if extraction_items:
                # Delete existing extractions for this document
                self.supabase.table("analysis_extractions").delete().eq(
                    "analysis_document_id", document_db_id
                ).execute()

                # Insert new extractions
                self.supabase.table("analysis_extractions").insert(
                    extraction_items
                ).execute()

            logger.debug(
                f"Successfully stored extraction for {doc_id} ({len(extraction_items)} items)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store extraction for document {doc_id}: {e}")
            return False

    async def store_document_chunks(
        self,
        project_id: str,
        doc_id: str,
        document_data: Dict[str, Any],
        full_text: str = None,
        use_abstracts_only: bool = False,
    ) -> bool:
        """
        Store document chunks for RAG. Creates summary, abstract, and content chunks.

        Args:
            project_id: The analysis project ID
            doc_id: The document ID (from analysis_documents.doc_id)
            document_data: Document metadata
            full_text: Full document text (if available)
            use_abstracts_only: Force abstract-only mode

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(
                f"Creating chunks for document {doc_id} in project {project_id}"
            )

            # First, get the analysis_documents.id (UUID) for this doc_id
            analysis_doc_result = (
                self.supabase.table("analysis_documents")
                .select("id")
                .eq("analysis_project_id", project_id)
                .eq("doc_id", doc_id)
                .execute()
            )

            if not analysis_doc_result.data:
                logger.error(
                    f"No analysis document found for doc_id {doc_id} in project {project_id}"
                )
                return False

            analysis_doc_uuid = analysis_doc_result.data[0]["id"]
            logger.debug(
                f"Found analysis document UUID {analysis_doc_uuid} for doc_id {doc_id}"
            )

            # Generate chunks
            chunks = chunk_document_text(
                full_text=full_text,
                title=document_data.get("title", ""),
                abstract=document_data.get("abstract_or_summary", ""),
                top_line=document_data.get("top_line", ""),
                relevance_reason=document_data.get("relevance_reason", ""),
                use_abstracts_only=use_abstracts_only,
            )

            if not chunks:
                logger.warning(f"No chunks generated for document {doc_id}")
                return False

            # Clean up existing chunks for this document UUID
            self.vectorization_service.supabase.table("chunks").delete().eq(
                "document_id", analysis_doc_uuid
            ).eq("project_id", project_id).execute()

            # Store chunks with embeddings (link to analysis_documents.id UUID)
            chunk_count = 0
            for chunk in chunks:
                try:
                    embedding = await self.vectorization_service.generate_embedding(
                        chunk.content
                    )

                    self.vectorization_service.supabase.table("chunks").insert(
                        {
                            "document_id": analysis_doc_uuid,  # Link to analysis_documents.id (UUID)
                            "project_id": project_id,
                            "content": chunk.content,
                            "chunk_type": chunk.chunk_type,
                            "chunk_index": chunk.chunk_index,
                            "embedding": embedding,
                            "token_count": chunk.token_count,
                        }
                    ).execute()

                    chunk_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to store chunk {chunk.chunk_index} for {doc_id}: {e}"
                    )
                    continue

            logger.info(
                f"Successfully stored {chunk_count}/{len(chunks)} chunks ({[c.chunk_type for c in chunks]}) for document {doc_id}"
            )
            return chunk_count > 0

        except Exception as e:
            logger.error(f"Failed to store chunks for document {doc_id}: {e}")
            return False

    async def update_documents_with_extractions(
        self, project_id: str, extractions_json_path: str
    ) -> None:
        """
        Update existing documents with extraction results.
        This is called after the extraction phase.

        Args:
            project_id: The analysis project ID
            extractions_json_path: Path to the extractions JSON file
        """
        logger.info(f"Updating documents with extractions from {extractions_json_path}")

        if not Path(extractions_json_path).exists():
            logger.warning(f"Extractions JSON not found: {extractions_json_path}")
            return

        # Load extractions JSON
        with open(extractions_json_path, "r", encoding="utf-8") as f:
            extractions_data = json.load(f)

        # Update documents with extraction results
        updates = []
        for extraction in extractions_data.get("extractions", []):
            doc_id = extraction.get("paper_id")
            if doc_id:
                updates.append(
                    {
                        "doc_id": doc_id,
                        "extraction_results": extraction,
                        "extraction_status": "completed",
                        "upload_step": "extracted",
                    }
                )

        if updates:
            await self._update_documents_by_doc_id(project_id, updates)
            logger.info(f"Updated {len(updates)} documents with extraction results")

    async def store_analysis_run(
        self,
        config: RunConfig,
        result: RunResult,
        project_id: str = None,
        user_id: str = None,
        user_name: str = None,
    ) -> str:
        """
        Store analysis run results to Supabase tables.

        Args:
            config: The analysis configuration
            result: The analysis results with file paths

        Returns:
            UUID of the created analysis_project record
        """
        logger.info(f"Starting Supabase storage for analysis run {result.run_id}")

        try:
            # 1. Create or update analysis project record
            if project_id:
                # Update existing project with run details
                storage_project_id = await self._update_analysis_project(
                    project_id, config, result
                )
            else:
                # Create new project record
                storage_project_id = await self._create_analysis_project(
                    config, result, user_id, user_name
                )

            # 2. Upload documents from references CSV
            await self._upload_documents(
                storage_project_id,
                result.references_csv_path,
                result.extractions_json_path,
            )

            # 3. Upload extractions from JSON (skip if interim storage was used)
            if result.extractions_json_path and not config.use_interim_storage:
                await self._upload_extractions(
                    storage_project_id, result.extractions_json_path
                )

            # 4. Mark project as completed
            await self._mark_project_completed(storage_project_id)

            logger.info(
                f"Successfully stored analysis run {result.run_id} to project {storage_project_id}"
            )
            return storage_project_id

        except Exception as e:
            logger.error(f"Failed to store analysis run {result.run_id}: {e}")
            # Try to mark project as failed if it was created
            try:
                await self._mark_project_failed(result.run_id, str(e))
            except Exception:
                pass
            raise

    async def _create_analysis_project(
        self,
        config: RunConfig,
        result: RunResult,
        user_id: str = None,
        user_name: str = None,
    ) -> str:
        """Create analysis_project record."""
        project_data = {
            "run_id": result.run_id,
            "title": f"{config.query[:50]}...",  # Auto-generate title from query
            "query": config.query,
            "total_references": result.total_references,
            "relevant_references": result.relevant_references,
            "status": "uploading",
            "created_by_user_id": user_id,
            "created_by_name": user_name,
        }

        response = (
            self.supabase.table("analysis_projects").insert(project_data).execute()
        )

        if not response.data:
            raise Exception("Failed to create analysis project record")

        project_id = response.data[0]["id"]
        logger.info(f"Created analysis project {project_id} for run {result.run_id}")
        return project_id

    async def _update_analysis_project(
        self, project_id: str, config: RunConfig, result: RunResult
    ) -> str:
        """Update existing analysis_project record with run details."""
        update_data = {
            "run_id": result.run_id,
            "total_references": result.total_references,
            "relevant_references": result.relevant_references,
            "status": "uploading",
        }

        response = (
            self.supabase.table("analysis_projects")
            .update(update_data)
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            raise Exception(f"Failed to update analysis project {project_id}")

        logger.info(f"Updated analysis project {project_id} for run {result.run_id}")
        return project_id

    async def _upload_documents(
        self,
        project_id: str,
        references_csv_path: str,
        extractions_json_path: Optional[str],
    ) -> None:
        """Upload documents from references CSV to analysis_documents table."""
        logger.info(f"Uploading documents from {references_csv_path}")

        # Load references CSV
        if not Path(references_csv_path).exists():
            raise FileNotFoundError(f"References CSV not found: {references_csv_path}")

        df = pd.read_csv(references_csv_path)
        logger.info(f"Found {len(df)} documents in references CSV")

        # Load extractions JSON if available to map extraction results
        extractions_map = {}
        if extractions_json_path and Path(extractions_json_path).exists():
            with open(extractions_json_path, "r", encoding="utf-8") as f:
                extractions_data = json.load(f)
                # Map doc_id to extraction results
                for extraction in extractions_data.get("extractions", []):
                    doc_id = extraction.get("paper_id")
                    if doc_id:
                        extractions_map[doc_id] = extraction

        # Prepare documents data using enhanced mapping
        documents_data = []
        for _, row in df.iterrows():
            # Create a temporary UnifiedReference-like object from the CSV row
            from .schemas import UnifiedReference

            try:
                # Map CSV data to UnifiedReference format
                ref_data = {
                    "doc_id": str(row.get("doc_id", "")),
                    "source": str(row.get("source", "")),
                    "source_id": str(row.get("source_id", "")),
                    "title": str(row.get("title", "")),
                    "abstract_or_summary": self._safe_str(
                        row.get("abstract_or_summary")
                    ),
                    "year": self._safe_int(row.get("year")),
                    "doi": self._safe_str(row.get("doi")),
                    "authors": self._parse_authors_simple(row.get("authors")),
                    "landing_page_url": self._safe_str(row.get("landing_page_url")),
                    "pdf_url": self._safe_str(row.get("pdf_url")),
                    "is_oa": self._safe_bool(row.get("is_oa")),
                    "type": self._safe_str(row.get("type")),
                    "author_institution_countries": self._parse_list_simple(
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
                    "document_type_reason": self._safe_str(
                        row.get("document_type_reason")
                    ),
                    # Essential fields: citation count and source country
                    "cited_by_count": self._safe_int(row.get("cited_by_count")),
                    "source_country": self._safe_str(row.get("source_country")),
                    # Acquisition fields
                    "acquisition_status": self._safe_str(row.get("acquisition_status")),
                    "acquisition_error": self._safe_str(row.get("acquisition_error")),
                    "full_text_available": self._safe_bool(
                        row.get("full_text_available")
                    ),
                    "file_path": self._safe_str(row.get("file_path")),
                    # Extraction fields
                    "extraction_status": self._safe_str(row.get("extraction_status")),
                    "extraction_error": self._safe_str(row.get("extraction_error")),
                    "text_source": self._safe_str(row.get("text_source")),
                }

                ref = UnifiedReference(**ref_data)

                # Use the enhanced mapping with extraction results and mark as completed
                doc_data = self._map_reference_to_document(
                    ref, project_id, upload_step="completed"
                )

                # Add extraction results if available
                doc_id = str(row.get("doc_id", ""))
                if doc_id in extractions_map:
                    doc_data["extraction_results"] = extractions_map[doc_id]
                    doc_data["extraction_status"] = "completed"

                documents_data.append(doc_data)

            except Exception as e:
                logger.warning(f"Failed to process document {row.get('doc_id')}: {e}")
                continue

        # Batch upsert documents (handles both new inserts and updates)
        if documents_data:
            await self._upsert_documents(documents_data)
            logger.info(f"Successfully uploaded {len(documents_data)} documents")

    async def _upload_extractions(
        self, project_id: str, extractions_json_path: str
    ) -> None:
        """Upload individual extraction items to analysis_extractions table."""
        logger.info(f"Uploading extractions from {extractions_json_path}")

        if not Path(extractions_json_path).exists():
            logger.warning(f"Extractions JSON not found: {extractions_json_path}")
            return

        with open(extractions_json_path, "r", encoding="utf-8") as f:
            extractions_data = json.load(f)

        # Get document IDs mapping
        doc_response = (
            self.supabase.table("analysis_documents")
            .select("id,doc_id")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        doc_id_map = {doc["doc_id"]: doc["id"] for doc in doc_response.data}

        extraction_items = []

        for extraction in extractions_data.get("extractions", []):
            paper_id = extraction.get("paper_id")
            if not paper_id or paper_id not in doc_id_map:
                logger.warning(f"Document {paper_id} not found in uploaded documents")
                continue

            document_id = doc_id_map[paper_id]
            bundle = DocumentExtractionBundle(**extraction)

            # Extract all types using helper method
            base_data = {
                "analysis_project_id": project_id,
                "analysis_document_id": document_id,
            }

            extraction_items.extend(self._create_extraction_items(bundle, base_data))

        # Batch insert extractions
        if extraction_items:
            batch_size = 100
            for i in range(0, len(extraction_items), batch_size):
                batch = extraction_items[i : i + batch_size]
                response = (
                    self.supabase.table("analysis_extractions").insert(batch).execute()
                )
                if not response.data:
                    raise Exception(
                        f"Failed to insert extractions batch {i//batch_size + 1}"
                    )

            logger.info(
                f"Successfully uploaded {len(extraction_items)} extraction items"
            )

    async def _mark_project_completed(self, project_id: str) -> None:
        """Mark analysis project as completed."""
        response = (
            self.supabase.table("analysis_projects")
            .update(
                {
                    "status": "completed",
                }
            )
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            raise Exception("Failed to mark project as completed")

        logger.info(f"Marked analysis project {project_id} as completed")

    async def _mark_project_failed(self, run_id: str, error_message: str) -> None:
        """Mark analysis project as failed."""
        try:
            response = (
                self.supabase.table("analysis_projects")
                .update(
                    {
                        "status": "failed",
                    }
                )
                .eq("run_id", run_id)
                .execute()
            )

            if response.data:
                logger.info(f"Marked analysis project {run_id} as failed")
        except Exception as e:
            logger.error(f"Failed to mark project as failed: {e}")

    def _create_extraction_items(
        self, bundle: DocumentExtractionBundle, base_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create extraction items from a document bundle."""
        items = []

        # Simplified extraction items with minimal fields + raw data
        extraction_types = [
            (
                "issue",
                bundle.issues,
                lambda x: (x.label, x.explanation, x.supporting_quote),
            ),
            (
                "intervention",
                bundle.interventions,
                lambda x: (x.name, x.description, x.supporting_quote),
            ),
            (
                "mapping",
                bundle.mappings,
                lambda x: (None, x.rationale, x.supporting_quote),
            ),
            (
                "result",
                bundle.results,
                lambda x: (x.outcome_variable, x.result_text, x.supporting_quote),
            ),
        ]

        for extraction_type, extraction_list, field_extractor in extraction_types:
            for item in extraction_list:
                label, description, quote = field_extractor(item)
                items.append(
                    {
                        **base_data,
                        "extraction_type": extraction_type,
                        "label": label,
                        "description": description,
                        "supporting_quote": quote,
                        "raw_data": item.model_dump(),
                    }
                )

        # Conclusion
        if bundle.conclusion:
            items.append(
                {
                    **base_data,
                    "extraction_type": "conclusion",
                    "label": bundle.conclusion.top_line_summary,
                    "description": bundle.conclusion.detailed_explanation,
                    "supporting_quote": bundle.conclusion.supporting_quote,
                    "raw_data": bundle.conclusion.model_dump(),
                }
            )

        return items

    def _convert_field(self, value: Any, field_type: type) -> Any:
        """Convert a field value to the specified type, handling NaN/None gracefully."""
        if pd.isna(value) or value is None:
            return None

        if field_type == str:
            return str(value).strip() if str(value).strip() else None
        elif field_type == int:
            try:
                return int(float(value))  # Handle string numbers
            except (ValueError, TypeError):
                return None
        elif field_type == float:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        elif field_type == bool:
            return bool(value)

        return value

    def _map_reference_to_document(
        self, ref: UnifiedReference, project_id: str, upload_step: str = "initial"
    ) -> Dict[str, Any]:
        """Map a UnifiedReference to a document record for the database."""
        # Start with core fields that should always exist
        doc_data = {
            "analysis_project_id": project_id,
            "doc_id": ref.doc_id,
            "source": ref.source,
            "title": ref.title,
            "abstract_or_summary": ref.abstract_or_summary,
            "year": ref.year,
            "is_relevant": ref.is_relevant,
            "extraction_status": ref.extraction_status,
        }

        # Add extended fields only if they exist in the schema
        # This allows gradual schema migration without breaking existing systems
        extended_fields = {
            "source_id": ref.source_id,
            "doi": ref.doi,
            "authors": ref.authors,
            "landing_page_url": ref.landing_page_url,
            "pdf_url": ref.pdf_url,
            "is_oa": ref.is_oa,
            "document_type": ref.type,
            "author_institution_countries": ref.author_institution_countries,
            # Relevance fields
            "relevance_confidence": ref.relevance_confidence,
            "relevance_reason": ref.relevance_reason,
            "top_line": ref.top_line,
            "document_type_reason": ref.document_type_reason,
            # Acquisition fields
            "acquisition_status": ref.acquisition_status,
            "acquisition_error": ref.acquisition_error,
            "full_text_available": ref.full_text_available,
            "file_path": ref.file_path,
            # Extraction fields
            "extraction_error": ref.extraction_error,
            "text_source": ref.text_source,
            # Essential fields for frontend compatibility (map to correct database column names)
            "citation_count": ref.cited_by_count,  # Database column is citation_count, not cited_by_count
            "source_country": ref.source_country,
            # Step tracking
            "upload_step": upload_step,
        }

        # Only add extended fields that have non-None values
        # This prevents database errors if columns don't exist yet
        for key, value in extended_fields.items():
            if value is not None:
                doc_data[key] = value

        return doc_data

    async def _upsert_documents(self, documents_data: List[Dict[str, Any]]) -> None:
        """Upsert documents to handle updates to existing records."""
        if not documents_data:
            return

        # Use insert with conflict resolution
        batch_size = 100
        for i in range(0, len(documents_data), batch_size):
            batch = documents_data[i : i + batch_size]

            # Try regular insert first for new documents
            try:
                response = (
                    self.supabase.table("analysis_documents").insert(batch).execute()
                )
                if response.data:
                    continue
            except Exception as e:
                # If insert fails due to conflicts, try individual upserts
                logger.warning(f"Batch insert failed, trying individual upserts: {e}")

                for doc in batch:
                    try:
                        # Check if document exists
                        existing = (
                            self.supabase.table("analysis_documents")
                            .select("id")
                            .eq("analysis_project_id", doc["analysis_project_id"])
                            .eq("doc_id", doc["doc_id"])
                            .eq("source", doc["source"])
                            .execute()
                        )

                        if existing.data:
                            # Update existing document
                            doc_id = existing.data[0]["id"]
                            update_doc = {
                                k: v
                                for k, v in doc.items()
                                if k not in ["analysis_project_id", "doc_id", "source"]
                            }
                            self.supabase.table("analysis_documents").update(
                                update_doc
                            ).eq("id", doc_id).execute()
                        else:
                            # Insert new document
                            self.supabase.table("analysis_documents").insert(
                                doc
                            ).execute()

                    except Exception as doc_error:
                        logger.error(
                            f"Failed to upsert document {doc.get('doc_id')}: {doc_error}"
                        )
                        continue

    async def _update_documents_by_doc_id(
        self, project_id: str, updates: List[Dict[str, Any]]
    ) -> None:
        """Update documents by doc_id."""
        for update in updates:
            doc_id = update.pop("doc_id")

            response = (
                self.supabase.table("analysis_documents")
                .update(update)
                .eq("analysis_project_id", project_id)
                .eq("doc_id", doc_id)
                .execute()
            )

            if not response.data:
                logger.warning(
                    f"Failed to update document {doc_id} in project {project_id}"
                )

    def _parse_list_field(self, value: Any) -> Optional[List[str]]:
        """Parse a field that might be a list, string, or null."""
        if pd.isna(value) or value is None or value == "":
            return None

        if isinstance(value, list):
            return [str(item) for item in value]

        if isinstance(value, str):
            value = value.strip()
            if value in ("", "[]"):
                return None

            # Try JSON parsing first
            try:
                parsed = json.loads(value)
                return (
                    [str(parsed)]
                    if not isinstance(parsed, list)
                    else [str(item) for item in parsed]
                )
            except json.JSONDecodeError:
                # Fallback to comma separation
                return [item.strip() for item in value.split(",") if item.strip()]

        return [str(value)]

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

    def _parse_authors_simple(self, value) -> List[str] | None:
        """Parse authors field which might be a string or list."""
        if pd.isna(value) or value is None or value == "":
            return None

        if isinstance(value, list):
            return [str(author) for author in value]

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

        # Try JSON parsing for list-like strings
        try:
            import json

            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                return [str(author) for author in parsed]
            elif isinstance(parsed, str):
                return [parsed]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback to comma separation
        return [author.strip() for author in str(value).split(",") if author.strip()]

    def _parse_list_simple(self, value) -> List[str] | None:
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
