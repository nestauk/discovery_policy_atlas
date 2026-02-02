from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd

from app.core.config import settings
from app.services.analysis.prompts import (
    BOOLEAN_QUERY_SYSTEM_PROMPT,
    SEMANTIC_QUERY_SYSTEM_PROMPT,
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
from .utils.doc_ids import stable_doc_id


logger = logging.getLogger(__name__)

SYSTEMATIC_REVIEW_CLAUSE = (
    '("systematic review" OR "meta-analysis" OR "narrative synthesis")'
)
RCT_CLAUSE = (
    '("randomized controlled trial" OR "randomised controlled trial" '
    'OR "randomized control trial" OR "randomised control trial")'
)
VARIANT_PRIORITY = {"systematic_review": 0, "rct": 1, "base": 2}


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
        return await self._generate_boolean_query(
            research_question=natural_query,
            population_selected=[],
            outcome_selected=[],
            screening_factors=[],
            geography=[],
            langfuse_handler=langfuse_handler,
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
        )

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

        return await self._generate_boolean_queries_multi(
            research_question=natural_query,
            population_selected=[],
            outcome_selected=[],
            screening_factors=[],
            geography=[],
            n_runs=n_runs,
            temperature=temperature,
            langfuse_handler=langfuse_handler,
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
        )

    def _build_context_message(
        self,
        research_question: str,
        population_selected: List[str],
        outcome_selected: List[str],
        screening_factors: List[str],
        geography: List[str],
    ) -> str:
        """Build context message from search context components."""
        context_parts = [f"User query: {research_question}"]
        if population_selected:
            context_parts.append(
                f"Population interests: {', '.join(population_selected)}"
            )
        if outcome_selected:
            context_parts.append(f"Outcome interests: {', '.join(outcome_selected)}")
        if geography:
            context_parts.append(f"Geography: {', '.join(geography)}")
        # skipping screening factors for now
        # if screening_factors:
        # context_parts.append(f"Screening factors: {', '.join(screening_factors)}")
        return "\n".join(context_parts)

    async def _generate_boolean_query(
        self,
        research_question: str,
        population_selected: List[str],
        outcome_selected: List[str],
        screening_factors: List[str],
        geography: List[str],
        langfuse_handler=None,
        session_id: str = None,
        project_id: str = None,
        user_id: str = None,
    ) -> str:
        """Generate a boolean query from search context."""
        logger.info("🔍 Generating boolean query from search context")

        try:
            llm = ChatOpenAI(
                model=settings.BOOLEAN_QUERY_MODEL,
                temperature=settings.BOOLEAN_QUERY_TEMPERATURE,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=1000,
            )

            messages = [
                SystemMessage(content=BOOLEAN_QUERY_SYSTEM_PROMPT),
                HumanMessage(
                    content=self._build_context_message(
                        research_question,
                        population_selected,
                        outcome_selected,
                        screening_factors,
                        geography,
                    )
                ),
            ]

            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:references",
                        "component:references.boolean_query_from_context",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "references.boolean_query_from_context"

            resp = await llm.ainvoke(messages, config=config)
            boolean_query = (resp.content or research_question).strip()

            logger.info("✅ Generated boolean query from context: '%s'", boolean_query)
            return boolean_query

        except Exception as e:
            logger.warning("❌ Boolean query generation from context failed: %s", e)
            logger.info("🔄 Falling back to original query: '%s'", research_question)
            return research_question

    async def _generate_boolean_queries_multi(
        self,
        research_question: str,
        population_selected: List[str],
        outcome_selected: List[str],
        screening_factors: List[str],
        geography: List[str],
        n_runs: int = 5,
        temperature: float = 1.0,
        langfuse_handler=None,
        session_id: str = None,
        project_id: str = None,
        user_id: str = None,
    ) -> List[str]:
        """Generate multiple boolean queries from search context with temperature for diversity."""
        logger.info(
            "🔍 Generating %d boolean queries from context (temp=%.1f)",
            n_runs,
            temperature,
        )

        queries = []

        try:
            llm = ChatOpenAI(
                model=settings.BOOLEAN_QUERY_MODEL,
                temperature=temperature,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=1000,
            )

            messages = [
                SystemMessage(content=BOOLEAN_QUERY_SYSTEM_PROMPT),
                HumanMessage(
                    content=self._build_context_message(
                        research_question,
                        population_selected,
                        outcome_selected,
                        screening_factors,
                        geography,
                    )
                ),
            ]

            for i in range(n_runs):
                config = {}
                if langfuse_handler:
                    config["callbacks"] = [langfuse_handler]
                    config["metadata"] = build_langfuse_metadata(
                        tags=[
                            "component:references",
                            "component:references.boolean_query_from_context",
                            "mode:multi",
                            f"iteration:{i+1}",
                        ],
                        session_id=session_id,
                        user_id=user_id,
                        project_id=project_id,
                        extra={"iteration": i + 1, "total_runs": n_runs},
                    )
                    config["run_name"] = "references.boolean_query_from_context"

                resp = await llm.ainvoke(messages, config=config)
                boolean_query = (resp.content or "").strip()

                if boolean_query:
                    queries.append(boolean_query)
                    logger.debug("Query %d/%d: '%s'", i + 1, n_runs, boolean_query)

            # Remove exact duplicates while preserving order
            unique_queries = list(dict.fromkeys(queries))
            logger.info(
                "✅ Generated %d queries (%d unique) from context for multi-query search",
                len(queries),
                len(unique_queries),
            )

            return unique_queries

        except Exception as e:
            logger.warning("❌ Multi-query generation from context failed: %s", e)
            logger.info("🔄 Falling back to single query with original text")
            return [research_question]

    async def _generate_semantic_query(
        self,
        research_question: str,
        population_selected: List[str],
        outcome_selected: List[str],
        screening_factors: List[str],
        geography: List[str],
        langfuse_handler=None,
        session_id: str = None,
        project_id: str = None,
        user_id: str = None,
    ) -> str:
        """Generate a semantic query from search context."""
        logger.info("🔍 Generating semantic query from search context")

        try:
            model = settings.LLM_MODEL

            # Build context message
            context_parts = [f"Research question: {research_question}"]
            if population_selected:
                context_parts.append(
                    f"Population interests: {', '.join(population_selected)}"
                )
            if outcome_selected:
                context_parts.append(
                    f"Outcome interests: {', '.join(outcome_selected)}"
                )
            if screening_factors:
                context_parts.append(
                    f"Screening factors: {', '.join(screening_factors)}"
                )
            if geography:
                context_parts.append(f"Geography: {', '.join(geography)}")

            llm = ChatOpenAI(
                model=model,
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=500,
            )

            messages = [
                SystemMessage(content=SEMANTIC_QUERY_SYSTEM_PROMPT),
                HumanMessage(content="\n".join(context_parts)),
            ]

            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:references",
                        "component:references.semantic_query_from_context",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "references.semantic_query_from_context"

            resp = await llm.ainvoke(messages, config=config)
            semantic_query = (resp.content or research_question).strip()

            logger.info(
                "✅ Generated semantic query from context: '%s'", semantic_query
            )
            return semantic_query

        except Exception as e:
            logger.warning("❌ Semantic query generation from context failed: %s", e)
            logger.info("🔄 Falling back to original query: '%s'", research_question)
            return research_question

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
        search_context: Optional[Dict] = None,
        enable_rct_sysrev_fanout: Optional[bool] = None,
    ) -> tuple[Path, List[str], Optional[str]]:
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
            enable_rct_sysrev_fanout: Override to enable/disable RCT/systematic review fanout
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
        task_meta = []  # Track task types and variants for gathered results
        openalex_service = OpenAlexService() if "openalex" in sources else None
        overton_service = OvertonService() if "overton" in sources else None

        # Parse optional dates
        df_val = date.fromisoformat(date_from) if date_from else None
        dt_val = date.fromisoformat(date_to) if date_to else None

        # Determine OpenAlex query string(s) and track the boolean queries
        openalex_queries = []  # List of queries to execute
        boolean_queries_list = []  # List of all boolean queries (for storage)
        final_semantic_query = None
        logger.info("🔎 Building references with mode: '%s'", mode)
        logger.debug("Original query: '%s'", query)

        context = (
            search_context.model_dump()
            if hasattr(search_context, "model_dump")
            else (search_context or {})
        )

        research_question = context.get("research_question", query)
        population_selected = context.get("population", [])
        outcome_selected = context.get("outcome", [])
        screening_factors = context.get("screening_factors", [])

        geography_selected = context.get("geography", [])

        if context:
            logger.info("📋 Using search context for query generation")
        else:
            logger.info("📋 No search context provided; using query text only")

        # Generate boolean queries for OpenAlex
        openalex_query_variants = []  # {"query": str, "variant": str}
        if "openalex" in sources:
            if mode == "boolean" and boolean_query:
                openalex_queries = [boolean_query]
                boolean_queries_list = openalex_queries
                logger.info("📋 Using provided boolean query: '%s'", boolean_query)
            elif use_multi_query:
                logger.info(
                    "🔄 Multi-query mode: generating %d queries from context (temp=%.1f)",
                    n_runs,
                    temperature,
                )
                openalex_queries = await self._generate_boolean_queries_multi(
                    research_question=research_question,
                    population_selected=population_selected,
                    outcome_selected=outcome_selected,
                    screening_factors=screening_factors,
                    geography=geography_selected,
                    n_runs=n_runs,
                    temperature=temperature,
                    langfuse_handler=langfuse_handler,
                    session_id=session_id,
                    project_id=project_id,
                    user_id=user_id,
                )
                boolean_queries_list = openalex_queries
                logger.info(
                    "✅ Generated %d unique queries from context",
                    len(openalex_queries),
                )
            else:
                logger.info(
                    "🎯 Single-query mode: generating deterministic query from context (temp=0)"
                )
                single_query = await self._generate_boolean_query(
                    research_question=research_question,
                    population_selected=population_selected,
                    outcome_selected=outcome_selected,
                    screening_factors=screening_factors,
                    geography=geography_selected,
                    langfuse_handler=langfuse_handler,
                    session_id=session_id,
                    project_id=project_id,
                    user_id=user_id,
                )
                openalex_queries = [single_query]
                boolean_queries_list = [single_query]

            # Fan out each boolean query with systematic review and RCT variants
            fanout_enabled = (
                enable_rct_sysrev_fanout
                if enable_rct_sysrev_fanout is not None
                else settings.OPENALEX_ENABLE_RCT_SYSREV_FANOUT
            )

            seen_queries = set()

            def _add_variant(q: str, variant: str):
                if q not in seen_queries:
                    openalex_query_variants.append({"query": q, "variant": variant})
                    seen_queries.add(q)

            for base_query in openalex_queries:
                _add_variant(base_query, "base")
                if fanout_enabled:
                    _add_variant(
                        f"({base_query}) AND {SYSTEMATIC_REVIEW_CLAUSE}",
                        "systematic_review",
                    )
                    _add_variant(f"({base_query}) AND {RCT_CLAUSE}", "rct")

            boolean_queries_list = [item["query"] for item in openalex_query_variants]

        # Generate semantic query for Overton from context (skip if boolean-only)
        if "overton" in sources and mode != "boolean":
            final_semantic_query = await self._generate_semantic_query(
                research_question=research_question,
                population_selected=population_selected,
                outcome_selected=outcome_selected,
                screening_factors=screening_factors,
                geography=geography_selected,
                langfuse_handler=langfuse_handler,
                session_id=session_id,
                project_id=project_id,
                user_id=user_id,
            )

        # Execute OpenAlex queries
        if openalex_service:
            for idx, query_info in enumerate(openalex_query_variants):
                query_str = query_info["query"]
                query_variant = query_info["variant"]
                logger.info(
                    "🔍 Executing OpenAlex query %d/%d (%s): '%s'",
                    idx + 1,
                    len(openalex_query_variants),
                    query_variant,
                    query_str[:100] + ("..." if len(query_str) > 100 else ""),
                )

                tasks.append(
                    openalex_service.search(
                        query=query_str,
                        max_results=limit,
                        min_citations=settings.DEFAULT_MIN_CITATIONS,
                        date_from=df_val,
                        date_to=dt_val,
                    )
                )
                task_meta.append(("openalex_search", query_variant))

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
                    task_meta.append(("openalex_raw", query_variant))

        if overton_service:
            # Determine source_country parameter from geography_filter
            source_country = (
                geography_filter[0]
                if geography_filter and len(geography_filter) > 0
                else None
            )

            overton_semantic_query = final_semantic_query or research_question
            overton_boolean_query = boolean_query or (
                openalex_queries[0] if openalex_queries else research_question
            )

            # Overton supports semantic search directly; when boolean mode is requested,
            # pass the boolean query via query= and disable semantic.
            if mode == "semantic":
                logger.info(
                    "🔍 Overton semantic search with query: '%s', geography: %s",
                    overton_semantic_query,
                    source_country,
                )
                tasks.append(
                    overton_service.search(
                        query=overton_semantic_query,
                        max_results=limit,
                        semantic_search=True,
                        source_country=source_country,
                        published_after=df_val,
                        published_before=dt_val,
                    )
                )
                task_meta.append(("overton_search", None))
            else:
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
                task_meta.append(("overton_search", None))
            # Add raw Overton first-page JSON for debugging
            # Use the same query parameters as the search() call above
            tasks.append(
                overton_service.fetch_raw(
                    **(
                        {"squery": overton_semantic_query}
                        if mode == "semantic"
                        else {"query": overton_boolean_query}
                    ),
                    min_similarity=0.3,
                    pp=limit if limit and limit < 50 else 50,
                    source_country=source_country,
                    published_after=df_val,
                    published_before=dt_val,
                )
            )
            task_meta.append(("overton_raw", None))

        results: List[pd.DataFrame] = []
        raw_openalex: list = []
        raw_overton: dict | list | None = None
        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for meta, g in zip(task_meta, gathered):
                task_kind, task_variant = meta

                if isinstance(g, Exception):
                    logger.error("Reference fetch error (%s): %s", task_kind, g)
                    continue

                if task_kind == "openalex_search" and isinstance(g, pd.DataFrame):
                    df_tagged = g.copy()
                    df_tagged["query_variant"] = task_variant
                    results.append(df_tagged)
                elif task_kind == "openalex_raw" and isinstance(g, list):
                    raw_openalex.append({"variant": task_variant, "data": g})
                elif task_kind == "overton_search" and isinstance(g, pd.DataFrame):
                    results.append(g)
                elif task_kind == "overton_raw" and (
                    isinstance(g, dict) or isinstance(g, list)
                ):
                    raw_overton = g
                elif isinstance(g, pd.DataFrame):
                    results.append(g)

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
                    "query_variant",
                    "variant_priority",
                ]
            )
        else:
            frames: List[pd.DataFrame] = []
            for idx, df in enumerate(results):
                # Skip empty DataFrames
                if df.empty:
                    continue

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
                    variant_col = pd.Series([None] * len(df))
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
                    variant_col = df.get("query_variant", pd.Series([None] * len(df)))

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
                        "query_variant": variant_col,
                        "variant_priority": pd.Series(
                            [VARIANT_PRIORITY.get(v, 99) for v in variant_col]
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
                            "query_variant",
                            "variant_priority",
                        ]
                    ]
                )

            df = pd.concat(frames, ignore_index=True)

            if "variant_priority" not in df.columns:
                df["variant_priority"] = 99

            df = df.sort_values(
                ["relevance_score", "variant_priority"],
                ascending=[False, True],
            ).drop_duplicates(subset=["doc_id"])

            # Log combination statistics
            if len(frames) > 1:
                logger.info(
                    "📊 Combined %d source dataframes into %d unique documents",
                    len(frames),
                    len(df),
                )

        # If we got more results than limit due to multiple queries, trim them
        # BUT: trim OpenAlex and Overton separately to preserve Overton results
        should_trim = (
            limit
            and len(df) > limit
            and (use_multi_query or len(openalex_query_variants) > 1)
        )
        if should_trim:
            logger.info(
                "✂️ Trimming results from %d to %d (limit)",
                len(df),
                limit,
            )

            # Separate OpenAlex and Overton results
            openalex_df = df[df["source"] == "openalex"].copy()
            overton_df = df[df["source"] == "overton"].copy()

            # Trim OpenAlex results by relevance_score, keep all Overton results
            if len(openalex_df) > 0 and "relevance_score" in openalex_df.columns:
                if "variant_priority" not in openalex_df.columns:
                    openalex_df["variant_priority"] = 99

                openalex_df["variant_priority"] = pd.to_numeric(
                    openalex_df["variant_priority"], errors="coerce"
                ).fillna(99)

                openalex_df = openalex_df.sort_values(
                    ["relevance_score", "variant_priority"],
                    ascending=[False, True],
                ).head(limit)
                logger.info(
                    "  📊 Kept top %d OpenAlex results (priority then relevance), all %d Overton results",
                    len(openalex_df),
                    len(overton_df),
                )

            # Recombine
            df = pd.concat([openalex_df, overton_df], ignore_index=True)

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
        # Return list of boolean queries (or single query as list if none generated)
        if not boolean_queries_list:
            boolean_queries_list = [query]

        return references_csv, boolean_queries_list, final_semantic_query
