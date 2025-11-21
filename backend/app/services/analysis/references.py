from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.core.config import settings
from app.services.analysis.prompts import (
    BOOLEAN_QUERY_SYSTEM_PROMPT,
    BOOLEAN_QUERY_MULTI_SYSTEM_PROMPT,
)
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.openalex import OpenAlexService
from app.services.overton import OvertonService
from app.utils.geography import convert_country_codes_to_names
from app.utils.llm.llm_utils import (
    resolve_langfuse_session_id,
    get_langfuse_handler,
    build_langfuse_metadata,
)
from .utils_doc_ids import stable_doc_id


logger = logging.getLogger(__name__)


class ReferencesService:
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = Path(export_dir or settings.EXPORT_FILES_DIR)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def generate_boolean_query(
        self,
        natural_query: str,
        langfuse_handler=None,
        session_id: str = None,
        project_id: str = None,
        user_id: str = None,
    ) -> str:
        """Generate a boolean query deterministically (temperature 0)."""
        logger.info("🔍 Generating boolean query for: '%s'", natural_query)

        try:
            model = settings.BOOLEAN_QUERY_MODEL

            # Create LLM instance
            llm = ChatOpenAI(
                model=model,
                temperature=settings.BOOLEAN_QUERY_TEMPERATURE,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=1000,
            )

            messages = [
                SystemMessage(content=BOOLEAN_QUERY_SYSTEM_PROMPT),
                HumanMessage(content=natural_query),
            ]

            # Build config with callbacks and metadata
            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:references",
                        "component:references.boolean_query",
                        "mode:single",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "references.boolean_query"

            resp = await llm.ainvoke(messages, config=config)
            boolean_query = (resp.content or natural_query).strip()

            logger.info("✅ Generated boolean query: '%s'", boolean_query)
            return boolean_query

        except Exception as e:
            logger.warning("❌ Boolean query generation failed: %s", e)
            logger.info("🔄 Falling back to original query: '%s'", natural_query)
            return natural_query

    async def generate_boolean_queries_multi(
        self,
        natural_query: str,
        n_runs: int = 5,
        temperature: float = 1.0,
        model: str = None,
        langfuse_handler=None,
        session_id: str = None,
        project_id: str = None,
        user_id: str = None,
    ) -> List[str]:
        """Generate multiple boolean queries with temperature for diversity.

        This method generates multiple diverse boolean queries by using temperature > 0,
        then deduplicates them. Based on R&D findings showing that combining results
        from multiple diverse queries improves coverage.

        Args:
            natural_query: The research question in natural language
            n_runs: Number of different queries to generate
            temperature: Temperature for LLM generation (higher = more diverse)
            model: LLM model to use (defaults to settings.BOOLEAN_QUERY_MODEL)
            langfuse_handler: Langfuse callback handler for tracking
            session_id: Session ID for grouping traces
            project_id: Project ID for metadata
            user_id: User ID for metadata

        Returns:
            List of unique boolean query strings
        """
        logger.info(
            "🔍 Generating %d boolean queries (temp=%.1f) for: '%s'",
            n_runs,
            temperature,
            natural_query,
        )

        model = model or settings.BOOLEAN_QUERY_MODEL
        queries = []

        try:
            # Create LLM instance
            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=1000,
            )

            messages = [
                SystemMessage(content=BOOLEAN_QUERY_MULTI_SYSTEM_PROMPT),
                HumanMessage(content=natural_query),
            ]

            for i in range(n_runs):
                # Build config with callbacks and metadata
                config = {}
                if langfuse_handler:
                    config["callbacks"] = [langfuse_handler]
                    config["metadata"] = build_langfuse_metadata(
                        tags=[
                            "component:references",
                            "component:references.boolean_query",
                            "mode:multi",
                            f"iteration:{i+1}",
                        ],
                        session_id=session_id,
                        user_id=user_id,
                        project_id=project_id,
                        extra={"iteration": i + 1, "total_runs": n_runs},
                    )
                    config["run_name"] = "references.boolean_query"

                resp = await llm.ainvoke(messages, config=config)
                boolean_query = (resp.content or "").strip()

                if boolean_query:
                    queries.append(boolean_query)
                    logger.debug("Query %d/%d: '%s'", i + 1, n_runs, boolean_query)

            # Remove exact duplicates while preserving order
            unique_queries = list(dict.fromkeys(queries))
            logger.info(
                "✅ Generated %d queries (%d unique) for multi-query search",
                len(queries),
                len(unique_queries),
            )

            return unique_queries

        except Exception as e:
            logger.warning("❌ Multi-query generation failed: %s", e)
            logger.info("🔄 Falling back to single query with original text")
            return [natural_query]

    async def build_references(
        self,
        query: str,
        sources: List[str],
        limit: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        mode: str = "semantic",  # "boolean" | "semantic"
        boolean_query: Optional[str] = None,
        geography_filter: Optional[List[str]] = None,
        use_multi_query: Optional[bool] = None,
        n_query_runs: Optional[int] = None,
        query_temperature: Optional[float] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> tuple[Path, str]:
        """Fetch and normalize references, write references.csv, and return its path.

        New multi-query mode generates multiple diverse queries and combines results
        for better coverage based on R&D findings.

        Args:
            query: Natural language query or boolean query
            sources: List of sources to search (e.g., ["openalex", "overton"])
            limit: Maximum number of results to return
            date_from: Start date filter (ISO format)
            date_to: End date filter (ISO format)
            mode: Search mode - "boolean" or "semantic"
            boolean_query: Pre-defined boolean query (used in boolean mode)
            geography_filter: List of country codes to filter by
            use_multi_query: Enable multi-query mode (None = use config default)
            n_query_runs: Number of queries to generate in multi-query mode
            query_temperature: Temperature for query generation diversity
            project_id: Project ID for langfuse tracking
            user_id: User ID for langfuse tracking
        """

        # Initialize Langfuse handler for tracking
        session_id = resolve_langfuse_session_id(project_id)
        langfuse_handler = get_langfuse_handler(session_id=session_id)

        # Determine whether to use multi-query mode
        if use_multi_query is None:
            use_multi_query = settings.BOOLEAN_QUERY_GENERATION_MODE == "multi"

        n_runs = n_query_runs or settings.BOOLEAN_QUERY_N_RUNS
        temperature = query_temperature or settings.BOOLEAN_QUERY_TEMPERATURE

        tasks = []
        openalex_service = OpenAlexService() if "openalex" in sources else None
        overton_service = OvertonService() if "overton" in sources else None

        # Parse optional dates
        df_val = date.fromisoformat(date_from) if date_from else None
        dt_val = date.fromisoformat(date_to) if date_to else None

        # Determine OpenAlex query string(s) and track the final boolean query
        openalex_queries = []  # List of queries to execute
        final_boolean_query = None
        logger.info("🔎 Building references with mode: '%s'", mode)
        logger.debug("Original query: '%s'", query)

        if mode == "boolean":
            # Boolean mode: use provided query directly
            openalex_queries = [boolean_query or query]
            final_boolean_query = openalex_queries[0]
            logger.info("📋 Using provided boolean query: '%s'", final_boolean_query)

        elif mode == "semantic":
            logger.info(
                "🧠 Semantic mode: generating boolean query from natural language"
            )

            if use_multi_query:
                # Multi-query mode: generate multiple diverse queries
                logger.info(
                    "🔄 Multi-query mode: generating %d queries (temp=%.1f)",
                    n_runs,
                    temperature,
                )
                openalex_queries = await self.generate_boolean_queries_multi(
                    natural_query=query,
                    n_runs=n_runs,
                    temperature=temperature,
                    langfuse_handler=langfuse_handler,
                    session_id=session_id,
                    project_id=project_id,
                    user_id=user_id,
                )
                # Store all queries for debugging
                final_boolean_query = " | ".join(openalex_queries)
                logger.info("✅ Generated %d unique queries", len(openalex_queries))
            else:
                # Single-query mode: generate one deterministic query
                logger.info(
                    "🎯 Single-query mode: generating deterministic query (temp=0)"
                )
                single_query = await self.generate_boolean_query(
                    natural_query=query,
                    langfuse_handler=langfuse_handler,
                    session_id=session_id,
                    project_id=project_id,
                    user_id=user_id,
                )
                openalex_queries = [single_query]
                final_boolean_query = single_query

        # Execute OpenAlex queries
        if openalex_service:
            for idx, query_str in enumerate(openalex_queries):
                logger.info(
                    "🔍 Executing OpenAlex query %d/%d: '%s'",
                    idx + 1,
                    len(openalex_queries),
                    query_str[:100] + ("..." if len(query_str) > 100 else ""),
                )

                tasks.append(
                    openalex_service.search(
                        query=query_str,
                        max_results=limit if len(openalex_queries) == 1 else None,
                        min_citations=settings.DEFAULT_MIN_CITATIONS,
                        date_from=df_val,
                        date_to=dt_val,
                    )
                )

                # Also collect raw responses for first query only (to avoid too much data)
                if idx == 0:
                    tasks.append(
                        openalex_service.fetch_raw(
                            query=query_str,
                            max_results=limit,
                            min_citations=settings.DEFAULT_MIN_CITATIONS,
                            date_from=df_val,
                            date_to=dt_val,
                        )
                    )

        if overton_service:
            # Determine source_country parameter from geography_filter
            source_country = (
                geography_filter[0]
                if geography_filter and len(geography_filter) > 0
                else None
            )

            # Overton supports semantic search directly; when boolean mode is requested,
            # pass the boolean query via query= and disable semantic.
            if mode == "semantic":
                logger.info(
                    "🔍 Overton semantic search with original query: '%s', geography: %s",
                    query,
                    source_country,
                )
                tasks.append(
                    overton_service.search(
                        query=query,
                        max_results=limit,
                        semantic_search=True,
                        source_country=source_country,
                        published_after=df_val,
                        published_before=dt_val,
                    )
                )
            else:
                overton_boolean_query = boolean_query or query
                logger.info(
                    "📋 Overton boolean search with query: '%s', geography: %s",
                    overton_boolean_query,
                    source_country,
                )
                tasks.append(
                    overton_service.search(
                        query=overton_boolean_query,
                        max_results=limit,
                        semantic_search=False,
                        source_country=source_country,
                        published_after=df_val,
                        published_before=dt_val,
                    )
                )
            # Add raw Overton first-page JSON for debugging
            tasks.append(
                overton_service.fetch_raw(
                    **(
                        {"squery": query}
                        if mode == "semantic"
                        else {"query": boolean_query or query}
                    ),
                    min_similarity=0.3,
                    pp=limit if limit and limit < 50 else 50,
                    source_country=source_country,
                    published_after=df_val,
                    published_before=dt_val,
                )
            )

        results: List[pd.DataFrame] = []
        raw_openalex: list = []
        raw_overton: dict | list | None = None
        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for g in gathered:
                if isinstance(g, Exception):
                    logger.error("Reference fetch error: %s", g)
                elif isinstance(g, pd.DataFrame):
                    results.append(g)
                elif isinstance(g, list) and openalex_service:
                    raw_openalex = g
                elif isinstance(g, dict) or isinstance(g, list):
                    raw_overton = g

        if not results:
            df = pd.DataFrame(
                columns=[
                    "doc_id",
                    "source",
                    "source_id",
                    "title",
                    "abstract_or_summary",
                    "year",
                    "doi",
                    "authors",
                    "landing_page_url",
                    "pdf_url",
                    "is_oa",
                    "type",
                    "cited_by_count",
                    "relevance_score",
                    "source_country",
                    "author_institution_countries",
                ]
            )
        else:
            frames: List[pd.DataFrame] = []
            for idx, df in enumerate(results):
                if "overton_url" in df.columns:
                    source = "overton"
                    source_id_col = "id"
                    doi_col = "doi"
                    year_col = "publication_year"
                    title_col = "title"
                    abs_col = "abstract"
                    landing_col = "landing_page_url"
                    pdf_col = "pdf_url"
                    type_value = df.get("source_type", pd.Series([None] * len(df)))
                    authors_col = "authors"
                else:
                    source = "openalex"
                    source_id_col = "id"
                    doi_col = "doi"
                    year_col = "publication_year"
                    title_col = "title"
                    abs_col = "abstract"
                    landing_col = "landing_page_url"
                    pdf_col = "pdf_url"
                    type_value = df.get("work_type", pd.Series([None] * len(df)))
                    authors_col = "authors"

                normalized = pd.DataFrame(
                    {
                        "source": source,
                        "source_id": df.get(
                            source_id_col, pd.Series([None] * len(df))
                        ).astype(str),
                        "title": df.get(title_col, pd.Series([None] * len(df))),
                        "abstract_or_summary": df.get(
                            abs_col, pd.Series([None] * len(df))
                        ),
                        "year": df.get(year_col, pd.Series([None] * len(df))),
                        "doi": df.get(doi_col, pd.Series([None] * len(df))),
                        "authors": df.get(authors_col, pd.Series([None] * len(df))),
                        "landing_page_url": df.get(
                            landing_col, pd.Series([None] * len(df))
                        ),
                        "pdf_url": df.get(pdf_col, pd.Series([None] * len(df))),
                        "is_oa": df.get("is_oa", pd.Series([None] * len(df))),
                        "type": type_value,
                        "cited_by_count": df.get(
                            "cited_by_count", pd.Series([None] * len(df))
                        ),
                        "relevance_score": df.get(
                            "relevance_score", pd.Series([0] * len(df))
                        ),
                    }
                )

                # Handle source_country differently for OpenAlex vs Overton
                if source == "openalex":
                    # For OpenAlex, convert author institution countries to readable names
                    if "author_institution_countries" in df.columns:
                        normalized["source_country"] = df[
                            "author_institution_countries"
                        ].apply(convert_country_codes_to_names)
                    else:
                        normalized["source_country"] = pd.Series([None] * len(df))
                else:
                    # For Overton, use the existing source_country field
                    normalized["source_country"] = df.get(
                        "source_country", pd.Series([None] * len(df))
                    )

                # Include author institution countries when available (OpenAlex)
                if "author_institution_countries" in df.columns:
                    normalized["author_institution_countries"] = df[
                        "author_institution_countries"
                    ].apply(
                        lambda v: v
                        if isinstance(v, list)
                        else ([] if pd.isna(v) else [v])
                    )
                else:
                    normalized["author_institution_countries"] = [
                        list() for _ in range(len(df))
                    ]

                # Build stable doc_ids
                normalized["doc_id"] = [
                    stable_doc_id(
                        doi=(
                            row["doi"]
                            if isinstance(row["doi"], str) and row["doi"]
                            else None
                        ),
                        source_id=row["source_id"],
                        title=row["title"],
                        year=int(row["year"]) if pd.notna(row["year"]) else None,
                    )
                    for _, row in normalized.iterrows()
                ]

                frames.append(
                    normalized[
                        [
                            "doc_id",
                            "source",
                            "source_id",
                            "title",
                            "abstract_or_summary",
                            "year",
                            "doi",
                            "authors",
                            "landing_page_url",
                            "pdf_url",
                            "is_oa",
                            "type",
                            "author_institution_countries",
                            "cited_by_count",
                            "source_country",
                            "relevance_score",
                        ]
                    ]
                )

            df = pd.concat(frames, ignore_index=True).drop_duplicates(
                subset=["doc_id"]
            )  # de-dupe by doc_id

            # Log combination statistics
            if len(frames) > 1:
                logger.info(
                    "📊 Combined %d source dataframes into %d unique documents",
                    len(frames),
                    len(df),
                )

        # If we got more results than limit due to multi-query, trim them
        if use_multi_query and len(df) > limit:
            logger.info(
                "✂️ Trimming results from %d to %d (limit) - keeping most cited papers",
                len(df),
                limit,
            )
            # Sort by relevance_score to keep most cited papers
            if "relevance_score" in df.columns:
                df = df.sort_values("relevance_score", ascending=False).head(limit)
            else:
                df = df.head(limit)

        # Ensure export directory exists
        self.export_dir.mkdir(parents=True, exist_ok=True)
        references_csv = self.export_dir / "references.csv"
        df.to_csv(references_csv, index=False)

        # Save raw payloads for debugging
        import json

        debug_dir = self.export_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        if raw_openalex:
            (debug_dir / "openalex_raw.json").write_text(
                json.dumps(raw_openalex, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if raw_overton is not None:
            (debug_dir / "overton_raw.json").write_text(
                json.dumps(raw_overton, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        logger.info("Wrote references.csv with %d rows to %s", len(df), references_csv)
        return references_csv, final_boolean_query or query
