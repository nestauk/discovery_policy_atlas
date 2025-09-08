from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.core.config import settings
from app.services.analysis.prompts import BOOLEAN_QUERY_SYSTEM_PROMPT
from openai import AsyncOpenAI
from app.services.openalex import OpenAlexService
from app.services.overton import OvertonService
from app.utils.geography import convert_country_codes_to_names
from .utils_doc_ids import stable_doc_id


logger = logging.getLogger(__name__)


class ReferencesService:
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = Path(export_dir or settings.EXPORT_FILES_DIR)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._openai_client: Optional[AsyncOpenAI] = None

    @property
    def openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY required for boolean query generation")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def generate_boolean_query(self, natural_query: str) -> str:
        """Generate a boolean query deterministically (temperature 0)."""
        logger.info("🔍 Generating boolean query for: '%s'", natural_query)

        try:
            resp = await self.openai_client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": BOOLEAN_QUERY_SYSTEM_PROMPT},
                    {"role": "user", "content": natural_query},
                ],
                max_tokens=1000,
            )
            boolean_query = (resp.choices[0].message.content or natural_query).strip()

            logger.info("✅ Generated boolean query: '%s'", boolean_query)
            if resp.usage:
                logger.debug(
                    "Token usage - Prompt: %d, Completion: %d, Total: %d",
                    resp.usage.prompt_tokens,
                    resp.usage.completion_tokens,
                    resp.usage.total_tokens,
                )

            return boolean_query
        except Exception as e:
            logger.warning("❌ Boolean query generation failed: %s", e)
            logger.info("🔄 Falling back to original query: '%s'", natural_query)
            return natural_query

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
    ) -> Path:
        """Fetch and normalize references, write references.csv, and return its path."""

        tasks = []
        openalex_service = OpenAlexService() if "openalex" in sources else None
        overton_service = OvertonService() if "overton" in sources else None

        # Parse optional dates
        df_val = date.fromisoformat(date_from) if date_from else None
        dt_val = date.fromisoformat(date_to) if date_to else None

        # Determine OpenAlex query string
        openalex_query_str = query
        logger.info("🔎 Building references with mode: '%s'", mode)
        logger.debug("Original query: '%s'", query)

        if mode == "boolean":
            openalex_query_str = boolean_query or query
            logger.info("📋 Using provided boolean query: '%s'", openalex_query_str)
        elif mode == "semantic":
            # Generate boolean query from natural query
            logger.info(
                "🧠 Semantic mode: generating boolean query from natural language"
            )
            openalex_query_str = await self.generate_boolean_query(query)
            logger.info("🎯 Final OpenAlex query string: '%s'", openalex_query_str)

        if openalex_service:
            tasks.append(
                openalex_service.search(
                    query=openalex_query_str,
                    max_results=limit,
                    min_citations=settings.DEFAULT_MIN_CITATIONS,
                    date_from=df_val,
                    date_to=dt_val,
                )
            )
            # Also collect raw OpenAlex responses for debugging
            tasks.append(
                openalex_service.fetch_raw(
                    query=openalex_query_str,
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
                        # Essential fields: citation count and source country
                        "cited_by_count": df.get(
                            "cited_by_count", pd.Series([None] * len(df))
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
                            # Essential new fields
                            "cited_by_count",
                            "source_country",
                        ]
                    ]
                )

            df = pd.concat(frames, ignore_index=True).drop_duplicates(
                subset=["doc_id"]
            )  # de-dupe by doc_id

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
        return references_csv
