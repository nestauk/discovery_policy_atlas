from __future__ import annotations

import asyncio
import logging
import math
from datetime import date
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

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
from .utils_doc_ids import stable_doc_id
from .relevance import RelevanceService


logger = logging.getLogger(__name__)

SYSTEMATIC_REVIEW_CLAUSE = (
    '("systematic review" OR "meta-analysis" OR "narrative synthesis")'
)
RCT_CLAUSE = '("randomised control trial" OR "randomized control trial" OR "randomised controlled trial" OR "randomized controlled trial" OR "randomised control trials" OR "randomized control trials")'


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
        relevance_cache_path: Optional[str] = None,
        enable_query_enrichment: Optional[bool] = None,
        enable_sampling_stopping: Optional[bool] = None,
        sampling_pages: Optional[List[int]] = None,
        sampling_stop_threshold: Optional[float] = None,
        sampling_max_depth: Optional[int] = None,
        sampling_page_size: Optional[int] = None,
    ) -> tuple[Path, List[str], Optional[str], Optional[Dict[str, Any]]]:
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
            relevance_cache_path: Path to reuse/store LLM relevance checks (JSONL)
            enable_query_enrichment: Toggle to add SR/RCT variants (default from settings)
            enable_sampling_stopping: Toggle to run sampling + early stop (default from settings)
            sampling_pages: Pages to sample for early stopping
            sampling_stop_threshold: Non-relevance threshold to stop (e.g., 0.75)
            sampling_max_depth: Max bisection depth for sampling refinement
            sampling_page_size: Page size for sampling and retrieval
        """

        # Initialize Langfuse handler for tracking
        session_id = resolve_langfuse_session_id(project_id)
        langfuse_handler = get_langfuse_handler(session_id=session_id)

        # Determine whether to use multi-query mode
        if use_multi_query is None:
            use_multi_query = settings.BOOLEAN_QUERY_GENERATION_MODE == "multi"

        n_runs = n_query_runs or settings.BOOLEAN_QUERY_N_RUNS
        temperature = query_temperature or settings.BOOLEAN_QUERY_TEMPERATURE
        enrichment_enabled = (
            enable_query_enrichment
            if enable_query_enrichment is not None
            else settings.QUERY_ENRICHMENT_ENABLED
        )
        sampling_enabled = (
            enable_sampling_stopping
            if enable_sampling_stopping is not None
            else settings.SAMPLING_STOP_ENABLED
        )
        # Derive sampling pages:
        # - If caller passes an explicit list, use it.
        # - Otherwise, build from interval up to max samples or MAX_SEARCH_RESULTS/page_size.
        if sampling_pages:
            sampling_pages_cfg = sampling_pages
        else:
            interval = settings.SAMPLING_PAGE_INTERVAL
            max_samples = settings.SAMPLING_MAX_SAMPLES
            max_pages_possible = max(
                1, (settings.MAX_SEARCH_RESULTS // sampling_page_size)
            )
            sampling_pages_cfg = [1]
            current = interval
            while (
                len(sampling_pages_cfg) < max_samples and current <= max_pages_possible
            ):
                sampling_pages_cfg.append(current)
                current += interval
        sampling_threshold = (
            sampling_stop_threshold
            if sampling_stop_threshold is not None
            else settings.SAMPLING_STOP_THRESHOLD
        )
        sampling_max_depth = (
            sampling_max_depth
            if sampling_max_depth is not None
            else settings.SAMPLING_MAX_DEPTH
        )
        sampling_page_size = (
            sampling_page_size
            if sampling_page_size is not None
            else settings.SAMPLING_PAGE_SIZE
        )
        sampling_metadata: List[Dict[str, Any]] = []
        relevance_cache = (
            Path(relevance_cache_path)
            if relevance_cache_path
            else self.export_dir / "relevance_cache.jsonl"
        )

        def _estimate_relevant_from_samples(
            samples: List[Dict[str, Any]],
            page_size: int,
            total_available: Optional[int],
        ) -> Optional[int]:
            """Estimate total relevant docs using trapezoidal interpolation + tail extrapolation."""
            if not samples:
                return None
            samples = sorted(samples, key=lambda x: x.get("page", 0))
            max_pages = (
                math.ceil(total_available / page_size)
                if total_available
                else samples[-1]["page"]
            )
            relevant_est = 0.0

            # Include the first sampled page
            first_rate = max(0.0, min(1.0, samples[0].get("relevant_rate", 0.0)))
            relevant_est += page_size * first_rate

            # Trapezoid between consecutive samples
            for i in range(len(samples) - 1):
                p1 = samples[i].get("page", 0)
                p2 = samples[i + 1].get("page", 0)
                if p2 <= p1:
                    continue
                r1 = max(0.0, min(1.0, samples[i].get("relevant_rate", 0.0)))
                r2 = max(0.0, min(1.0, samples[i + 1].get("relevant_rate", 0.0)))
                pages_range = p2 - p1
                items = pages_range * page_size
                avg_rate = (r1 + r2) / 2
                relevant_est += items * avg_rate

            last_sample = samples[-1]
            last_page = last_sample.get("page", 0)
            last_rate = max(0.0, min(1.0, last_sample.get("relevant_rate", 0.0)))

            if max_pages <= last_page:
                return int(round(relevant_est))

            # Tail extrapolation using linear fit over last up to 3 points
            tail_points = samples[-3:] if len(samples) >= 3 else samples[-2:]
            xs = [p.get("page", 0) for p in tail_points]
            ys = [max(0.0, min(1.0, p.get("relevant_rate", 0.0))) for p in tail_points]
            mean_x = sum(xs) / len(xs)
            mean_y = sum(ys) / len(ys)
            denom = sum((x - mean_x) ** 2 for x in xs)
            slope = (
                sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
                if denom > 0
                else 0.0
            )
            intercept = mean_y - slope * mean_x

            end_page = max_pages
            remaining_items = (
                max(0, total_available - last_page * page_size)
                if total_available is not None
                else (end_page - last_page) * page_size
            )
            if remaining_items <= 0:
                return int(round(relevant_est))

            if slope >= 0:
                tail_rate_end = last_rate
                tail_items = remaining_items
                relevant_est += tail_items * tail_rate_end
            else:
                rate_at_end = max(0.0, intercept + slope * end_page)
                tail_items = remaining_items
                avg_rate = max(0.0, (last_rate + rate_at_end) / 2)
                relevant_est += tail_items * avg_rate

            return int(round(relevant_est))

        tasks = []
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

        # Generate boolean queries for OpenAlex and enrich with SR/RCT variants
        enriched_openalex_queries: List[Dict[str, Any]] = []
        priority_map = {"systematic_review": 0, "rct": 1, "base": 2}

        if "openalex" in sources:
            if mode == "boolean" and boolean_query:
                openalex_queries = [boolean_query]
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

            # Enrich with SR / RCT variants (enabled by default)
            for idx, base_q in enumerate(openalex_queries):
                enriched_openalex_queries.append(
                    {
                        "query": base_q,
                        "variant": "base",
                        "priority": priority_map["base"],
                        "base_index": idx,
                    }
                )
                if enrichment_enabled:
                    enriched_openalex_queries.append(
                        {
                            "query": f"({base_q}) AND {SYSTEMATIC_REVIEW_CLAUSE}",
                            "variant": "systematic_review",
                            "priority": priority_map["systematic_review"],
                            "base_index": idx,
                        }
                    )
                    enriched_openalex_queries.append(
                        {
                            "query": f"({base_q}) AND {RCT_CLAUSE}",
                            "variant": "rct",
                            "priority": priority_map["rct"],
                            "base_index": idx,
                        }
                    )

            boolean_queries_list = [item["query"] for item in enriched_openalex_queries]

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

        openalex_results: List[pd.DataFrame] = []
        raw_openalex: list = []

        # Execute OpenAlex queries with sampling and enrichment
        if openalex_service and enriched_openalex_queries:
            sampling_relevance = RelevanceService(
                query=research_question,
                export_dir=str(self.export_dir),
                project_id=project_id,
                user_id=user_id,
                search_context=context,
                relevance_output_path=str(relevance_cache),
                keep_relevance_output=True,
            )

            async def _sample_query(
                query_str: str, variant: str
            ) -> Tuple[int, float, Dict[str, Any]]:
                """Sample pages, run LLM relevance, and decide cutoff."""

                def _build_documents(df_slice: pd.DataFrame) -> Dict[str, str]:
                    docs: Dict[str, str] = {}
                    for _, row in df_slice.iterrows():
                        doc_id = stable_doc_id(
                            doi=row.get("doi"),
                            source_id=row.get("id"),
                            title=row.get("title"),
                            year=row.get("publication_year"),
                        )
                        content = f"Title: {row.get('title', '')}\n\nAbstract: {row.get('abstract', '')}"
                        docs[doc_id] = content
                    return docs

                async def _get_page_slice(page_number: int) -> pd.DataFrame:
                    df_page = await openalex_service.search(
                        query=query_str,
                        max_results=None,
                        min_citations=settings.DEFAULT_MIN_CITATIONS,
                        date_from=df_val,
                        date_to=dt_val,
                        page=page_number,
                        per_page=sampling_page_size,
                    )
                    if df_page is None or df_page.empty:
                        return pd.DataFrame()
                    return df_page.copy()

                pages_checked: List[Dict[str, Any]] = []
                last_good: Tuple[int, float] | None = None
                last_bad: Tuple[int, float] | None = None

                for page in sampling_pages_cfg:
                    df_slice = await _get_page_slice(page)
                    if df_slice.empty:
                        pages_checked.append(
                            {"page": page, "total": 0, "relevant_rate": 0.0}
                        )
                        continue
                    docs = _build_documents(df_slice)
                    results_df = await sampling_relevance._screen_batch(
                        documents=docs,
                        session_name=f"sampling_p{page}",
                        output_path=relevance_cache,
                        keep_file=True,
                    )
                    rel_rate = (
                        results_df["is_relevant"].mean()
                        if not results_df.empty
                        else 0.0
                    )
                    pages_checked.append(
                        {
                            "page": page,
                            "total": len(df_slice),
                            "relevant_rate": rel_rate,
                        }
                    )
                    non_rel_rate = 1 - rel_rate
                    if non_rel_rate > sampling_threshold:
                        last_bad = (page, rel_rate)
                    else:
                        last_good = (page, rel_rate)

                    # Early exit if we already have a bad page
                    if last_bad:
                        break

                # Bisection refinement
                depth = 0
                while (
                    sampling_max_depth > 0
                    and depth < sampling_max_depth
                    and last_good
                    and last_bad
                    and abs(last_good[0] - last_bad[0]) > 1
                ):
                    mid_page = int((last_good[0] + last_bad[0]) / 2)
                    df_slice = await _get_page_slice(mid_page)
                    if df_slice.empty:
                        pages_checked.append(
                            {"page": mid_page, "total": 0, "relevant_rate": 0.0}
                        )
                        break
                    docs = _build_documents(df_slice)
                    results_df = await sampling_relevance._screen_batch(
                        documents=docs,
                        session_name=f"sampling_p{mid_page}",
                        output_path=relevance_cache,
                        keep_file=True,
                    )
                    rel_rate = (
                        results_df["is_relevant"].mean()
                        if not results_df.empty
                        else 0.0
                    )
                    pages_checked.append(
                        {
                            "page": mid_page,
                            "total": len(df_slice),
                            "relevant_rate": rel_rate,
                        }
                    )
                    non_rel_rate = 1 - rel_rate
                    if non_rel_rate > sampling_threshold:
                        last_bad = (mid_page, rel_rate)
                    else:
                        last_good = (mid_page, rel_rate)
                    depth += 1

                cutoff_page = (
                    last_good[0] if last_good else (last_bad[0] if last_bad else 1)
                )
                rate_at_cutoff = (
                    last_good[1] if last_good else (last_bad[1] if last_bad else 0.0)
                )

                sampling_metadata.append(
                    {
                        "query": query_str,
                        "variant": variant,
                        "pages_checked": sorted(pages_checked, key=lambda x: x["page"]),
                        "cutoff_page": cutoff_page,
                        "threshold": sampling_threshold,
                        "rate_at_cutoff": rate_at_cutoff,
                    }
                )

                return cutoff_page, rate_at_cutoff, sampling_metadata[-1]

            for idx, meta in enumerate(enriched_openalex_queries):
                query_str = meta["query"]
                variant = meta["variant"]
                priority = meta["priority"]

                logger.info(
                    "🔍 Executing OpenAlex query %d/%d [%s]: '%s'",
                    idx + 1,
                    len(enriched_openalex_queries),
                    variant,
                    query_str[:100] + ("..." if len(query_str) > 100 else ""),
                )

                cutoff_page = None
                rate_at_cutoff = None
                total_available = None

                if sampling_enabled:
                    try:
                        total_available = await openalex_service.search_minimal(
                            query=query_str,
                            min_citations=settings.DEFAULT_MIN_CITATIONS,
                            date_from=df_val,
                            date_to=dt_val,
                            count_only=True,
                        )
                    except Exception as e:
                        logger.warning("Count fetch failed for sampling: %s", e)
                        total_available = None
                    cutoff_page, rate_at_cutoff, _ = await _sample_query(
                        query_str, variant
                    )
                    if sampling_metadata:
                        sampling_metadata[-1]["total_available"] = total_available
                        sampling_metadata[-1][
                            "estimated_relevant"
                        ] = _estimate_relevant_from_samples(
                            sampling_metadata[-1]["pages_checked"],
                            sampling_page_size,
                            total_available,
                        )

                fetch_limit = limit if len(enriched_openalex_queries) == 1 else limit
                if sampling_enabled and cutoff_page:
                    fetch_limit = min(fetch_limit, cutoff_page * sampling_page_size)

                df_res = await openalex_service.search(
                    query=query_str,
                    max_results=fetch_limit,
                    min_citations=settings.DEFAULT_MIN_CITATIONS,
                    date_from=df_val,
                    date_to=dt_val,
                )

                if isinstance(df_res, pd.DataFrame) and not df_res.empty:
                    df_res["retrieval_query_type"] = variant
                    df_res["retrieval_priority"] = priority
                    df_res["sampling_cutoff_page"] = cutoff_page
                    df_res["sampling_total_available"] = total_available
                    df_res["sampling_rate_at_cutoff"] = rate_at_cutoff
                    openalex_results.append(df_res)

                # Collect raw responses for first query only (to avoid too much data)
                if idx == 0:
                    raw_openalex = await openalex_service.fetch_raw(
                        query=query_str,
                        max_results=fetch_limit,
                        min_citations=settings.DEFAULT_MIN_CITATIONS,
                        date_from=df_val,
                        date_to=dt_val,
                    )

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

        results: List[pd.DataFrame] = list(openalex_results)
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
                        "retrieval_query_type": df.get(
                            "retrieval_query_type",
                            pd.Series(
                                ["overton" if source == "overton" else "base"] * len(df)
                            ),
                        ),
                        "retrieval_priority": df.get(
                            "retrieval_priority",
                            pd.Series([3 if source == "overton" else 2] * len(df)),
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
                            "retrieval_query_type",
                            "retrieval_priority",
                        ]
                    ]
                )

            df = pd.concat(frames, ignore_index=True)
            df = df.sort_values(
                ["retrieval_priority", "relevance_score", "cited_by_count"],
                ascending=[True, False, False],
            ).drop_duplicates(subset=["doc_id"])

            # Log combination statistics
            if len(frames) > 1:
                logger.info(
                    "📊 Combined %d source dataframes into %d unique documents",
                    len(frames),
                    len(df),
                )

        # If we got more results than limit due to multi-query, trim them
        # BUT: trim OpenAlex and Overton separately to preserve Overton results
        if use_multi_query and len(df) > limit:
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
                openalex_df = openalex_df.sort_values(
                    ["retrieval_priority", "relevance_score"],
                    ascending=[True, False],
                ).head(limit)
                logger.info(
                    "  📊 Kept top %d OpenAlex results (sorted by relevance), all %d Overton results",
                    len(openalex_df),
                    len(overton_df),
                )

            # Recombine
            df = pd.concat([openalex_df, overton_df], ignore_index=True)

        # Update search context with sampling/comprehensiveness info
        if context is not None and sampling_metadata:
            estimated_total = sum(
                item["estimated_relevant"]
                for item in sampling_metadata
                if item.get("estimated_relevant") is not None
            )
            context["comprehensiveness_estimate"] = {
                "sampling": sampling_metadata,
                "estimated_relevant_total": estimated_total or None,
                "retrieved_count": len(df),
                "coverage_ratio": (
                    len(df) / estimated_total if estimated_total else None
                ),
            }

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

        return references_csv, boolean_queries_list, final_semantic_query, context
