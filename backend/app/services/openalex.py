from pyalex import Works, config
import pandas as pd
from typing import Dict, Optional, Tuple, List
from datetime import date
from openai import AsyncOpenAI
from app.core.config import settings
import logging
import asyncio
import httpx
import math

logger = logging.getLogger(__name__)


def sanitize_openalex_query(query: str) -> str:
    """
    Sanitize boolean query for OpenAlex compatibility.

    OpenAlex doesn't handle commas inside quoted phrases properly,
    so we remove them while preserving the query structure.

    Args:
        query: Boolean query string

    Returns:
        Sanitized query string safe for OpenAlex
    """
    import re

    # Find all quoted phrases and remove commas within them
    def remove_commas_in_quotes(match):
        quoted_text = match.group(0)
        # Remove commas inside the quotes
        return quoted_text.replace(",", "")

    # Pattern to match quoted strings (both single and double quotes)
    pattern = r'"[^"]*"'
    sanitized = re.sub(pattern, remove_commas_in_quotes, query)

    return sanitized


class OpenAlexService:
    def __init__(self):
        # Configure PyAlex
        if settings.OPENALEX_EMAIL:
            config.email = settings.OPENALEX_EMAIL
        config.max_retries = 3
        config.retry_backoff_factor = 0.5

        # Configure API key for OpenAlex (PyAlex has built-in support)
        if settings.OPENALEX_API_KEY:
            config.api_key = settings.OPENALEX_API_KEY
            self._api_key = settings.OPENALEX_API_KEY
            logger.info("OpenAlex API key configured")
        else:
            self._api_key = None
            logger.warning(
                "OpenAlex API key not configured - limited to 100 credits per day"
            )

        # Initialize OpenAI client for boolean query generation
        if settings.OPENAI_API_KEY:
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self._openai_client = None
            logger.warning(
                "OpenAI API key not configured - boolean query generation will be disabled"
            )

    async def search(
        self,
        query: str,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        return_n_total: bool = False,
    ) -> pd.DataFrame:
        """Search OpenAlex for papers using PyAlex

        Args:
            query: The search query to use
            max_results: The maximum number of results to return
            min_citations: The minimum number of citations to return
            date_from: The minimum date to return
            date_to: The maximum date to return
            return_n_total: Whether to return the total number of results matching the query

        Returns:
            pd.DataFrame: A DataFrame of the results (up to max_results)
            If return_n_total is True, returns tuple (pd.DataFrame, int) where int is the
            total count of all results matching the query (from meta.count in OpenAlex API)
        """

        # Build query with PyAlex
        works_query = Works().search_filter(title_and_abstract=query)

        # Add filters using PyAlex filter syntax
        if min_citations:
            works_query = works_query.filter(cited_by_count=f">{min_citations}")

        if date_from:
            works_query = works_query.filter(
                from_publication_date=date_from.isoformat()
            )

        if date_to:
            works_query = works_query.filter(to_publication_date=date_to.isoformat())

        # Get total count if requested
        n_total = None
        if return_n_total:
            n_total = works_query.count()

        # Get results directly into DataFrame
        results = []
        if max_results is None:
            # Fetch all results
            for page in works_query.paginate(per_page=200):
                results.extend(page)
        else:
            # Fetch up to max_results
            for page in works_query.paginate(
                per_page=min(200, max_results), n_max=max_results
            ):
                results.extend(page)

        # Apply pyalex trick to reinvert abstracts
        for page in results:
            page["abstract"] = page["abstract"]

        # Process results to extract all available metadata
        processed_results = []
        for i, page in enumerate(results):
            try:
                # Extract authors with proper null checks
                authors = []
                author_institution_countries = set()
                if page.get("authorships"):
                    for authorship in page["authorships"]:
                        if authorship and isinstance(authorship, dict):
                            author = authorship.get("author")
                            if author and isinstance(author, dict):
                                display_name = author.get("display_name")
                                if display_name:
                                    authors.append(display_name)
                            # Collect institution country codes
                            institutions = authorship.get("institutions") or []
                            if isinstance(institutions, list):
                                for inst in institutions:
                                    if isinstance(inst, dict):
                                        cc = inst.get("country_code")
                                        if cc:
                                            author_institution_countries.add(cc)

                # Extract publication date
                publication_date = None
                if page.get("publication_date"):
                    publication_date = page["publication_date"]
                elif page.get("publication_year"):
                    publication_date = f"{page['publication_year']}-01-01"

                # Extract venue/journal information with proper null checks
                venue = ""
                primary_location = page.get("primary_location")
                if primary_location and isinstance(primary_location, dict):
                    source = primary_location.get("source")
                    if source and isinstance(source, dict):
                        display_name = source.get("display_name")
                        if display_name:
                            venue = display_name
                # Access/links
                landing_page_url = None
                pdf_url = None
                primary_is_oa = None
                if isinstance(primary_location, dict):
                    landing_page_url = primary_location.get("landing_page_url")
                    pdf_url = primary_location.get("pdf_url")
                    primary_is_oa = primary_location.get("is_oa")

                # Prefer best_oa_location if available (mirrors typical OA handling)
                best_oa_location = page.get("best_oa_location") or {}
                open_access = page.get("open_access") or {}
                is_oa = (
                    best_oa_location.get("is_oa")
                    if isinstance(best_oa_location, dict)
                    and "is_oa" in best_oa_location
                    else open_access.get("is_oa", primary_is_oa)
                )
                oa_url = open_access.get("oa_url")
                if isinstance(best_oa_location, dict):
                    landing_page_url = (
                        best_oa_location.get("landing_page_url") or landing_page_url
                    )
                    pdf_url = best_oa_location.get("pdf_url") or pdf_url
                # Prefer explicit PDF url; fallback to oa_url
                pdf_url = pdf_url or oa_url

                # Extract citation count
                cited_by_count = page.get("cited_by_count", 0)

                # Extract relevance score
                relevance_score = page.get("relevance_score", 0)

                # Extract work type
                work_type = page.get("type_crossref", "unknown")

                processed_result = {
                    "id": page.get("id", ""),
                    "title": page.get("title", "No title available"),
                    "abstract": page.get("abstract", "No abstract available"),
                    "doi": page.get("doi", ""),
                    "authors": authors,
                    "publication_date": publication_date,
                    "publication_year": page.get("publication_year"),
                    "venue": venue,
                    "cited_by_count": cited_by_count,
                    "relevance_score": relevance_score,
                    "work_type": work_type,
                    "source_country": "Academic",  # OpenAlex is academic literature
                    "source_type": "Academic Paper",
                    "landing_page_url": landing_page_url,
                    "pdf_url": pdf_url,
                    "is_oa": is_oa,
                    "author_institution_countries": sorted(author_institution_countries)
                    if author_institution_countries
                    else [],
                }
                processed_results.append(processed_result)
            except Exception as e:
                logger.error(f"Error processing result {i}: {e}")
                logger.error(f"Problematic page data: {page}")
                continue

        df = pd.DataFrame(processed_results)

        # Handle empty results
        if df.empty:
            if return_n_total:
                return df, 0
            else:
                return df

        # Clean up the data
        df["abstract"] = df["abstract"].fillna("No abstract available")
        df["content"] = df["abstract"].str[:1000]  # Limit content to first 1000 chars
        df["title"] = df["title"].fillna("No title available")
        df["doi"] = df["doi"].fillna("")
        df["authors"] = df["authors"].apply(
            lambda x: x if isinstance(x, list) and len(x) > 0 else ["Unknown"]
        )
        df["publication_date"] = df["publication_date"].fillna("")
        # Handle publication_year properly - convert NaN to None for missing years
        df["publication_year"] = df["publication_year"].where(
            df["publication_year"].notna(), None
        )
        df["venue"] = df["venue"].fillna("")
        df["cited_by_count"] = df["cited_by_count"].fillna(0)
        df["relevance_score"] = df["relevance_score"].fillna(0)
        df["work_type"] = df["work_type"].fillna("unknown")
        df["source_country"] = df["source_country"].fillna("Academic")
        df["source_type"] = df["source_type"].fillna("Academic Paper")

        if return_n_total:
            return df, n_total
        else:
            return df

    async def search_minimal(
        self,
        query: str,
        max_results: Optional[int] = settings.DEFAULT_MAX_RESULTS,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        return_n_total: bool = False,
        count_only: bool = False,
        fields: list[str] = ["id", "doi", "title", "cited_by_count", "relevance_score"],
    ) -> pd.DataFrame | Tuple[pd.DataFrame, int] | int:
        """Minimal search that only returns id, DOI, and title fields

        Args:
            query: The search query to use
            max_results: The maximum number of results to return. If None, fetches all results.
            min_citations: The minimum number of citations to return
            date_from: The minimum date to return
            date_to: The maximum date to return
            return_n_total: Whether to return the total number of results matching the query
            count_only: If True, only return the count without fetching any results

        Returns:
            pd.DataFrame: A DataFrame with only id, doi, and title columns
            If return_n_total is True, returns tuple (pd.DataFrame, int) where int is the
            total count of all results matching the query (from meta.count in OpenAlex API)
            If count_only is True, returns only int (the total count)
        """
        # Sanitize query for OpenAlex compatibility (removes commas from quoted phrases)
        sanitized_query = sanitize_openalex_query(query)
        logger.debug(f"Original query: {query}")
        logger.debug(f"Sanitized query: {sanitized_query}")

        # Build query with PyAlex
        works_query = Works().search_filter(title_and_abstract=sanitized_query)

        # Add filters using PyAlex filter syntax
        if min_citations:
            works_query = works_query.filter(cited_by_count=f">{min_citations}")

        if date_from:
            works_query = works_query.filter(
                from_publication_date=date_from.isoformat()
            )

        if date_to:
            works_query = works_query.filter(to_publication_date=date_to.isoformat())

        # Select only the essential fields
        works_query = works_query.select(fields)

        # Get total count if requested or if count_only
        n_total = None
        if return_n_total or count_only:
            n_total = works_query.count()

        # If only count is requested, return early
        if count_only:
            return n_total

        # Get results directly into DataFrame
        results = []
        if max_results is None:
            # Fetch all results
            for page in works_query.paginate(per_page=200):
                results.extend(page)
        else:
            # Fetch up to max_results
            for page in works_query.paginate(
                per_page=min(200, max_results), n_max=max_results
            ):
                results.extend(page)

        # Extract only essential fields
        minimal_results = []
        for page in results:
            minimal_results.append(
                {
                    "id": page.get("id", ""),
                    "doi": page.get("doi", ""),
                    "title": page.get("title", ""),
                    "cited_by_count": page.get("cited_by_count", 0),
                    "relevance_score": page.get("relevance_score", 0),
                }
            )

        # Convert to DataFrame
        df = pd.DataFrame(minimal_results)

        if return_n_total:
            return df, n_total
        else:
            return df

    async def search_multi_query(
        self,
        queries: List[str],
        max_results_per_query: Optional[int] = None,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> pd.DataFrame:
        """Execute multiple queries and combine results, removing duplicates.

        This method is designed for multi-query search strategies where multiple
        diverse boolean queries are generated and their results are combined
        for better coverage.

        Args:
            queries: List of boolean query strings
            max_results_per_query: Max results per individual query (None = unlimited)
            min_citations: Minimum citation count filter
            date_from: Filter by minimum publication date
            date_to: Filter by maximum publication date

        Returns:
            Combined DataFrame with duplicates removed by ID
        """
        logger.info(
            "🔍 Executing %d queries and combining results (de-duplicating by ID)",
            len(queries),
        )

        # Execute all queries concurrently
        tasks = [
            self.search(
                query=q,
                max_results=max_results_per_query,
                min_citations=min_citations,
                date_from=date_from,
                date_to=date_to,
            )
            for q in queries
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        valid_dfs = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error("Query %d failed: %s", i + 1, r)
            elif isinstance(r, pd.DataFrame):
                valid_dfs.append(r)

        if not valid_dfs:
            logger.warning("❌ No valid results from any query")
            return pd.DataFrame()

        # Concatenate and de-duplicate by ID
        combined = pd.concat(valid_dfs, ignore_index=True)
        deduped = combined.drop_duplicates(subset=["id"], keep="first")

        logger.info(
            "✅ Combined %d results from %d queries → %d unique documents",
            len(combined),
            len(valid_dfs),
            len(deduped),
        )

        return deduped

    def format_for_screening(self, df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
        """Format papers for LLM screening"""
        # Create dictionary with title and content
        return df.set_index("id")[["title", "content"]].to_dict("index")

    async def check_rate_limit(self) -> Optional[Dict]:
        """Check current OpenAlex rate limit status.

        Returns:
            Dict with rate limit information, or None if API key is not configured
        """
        if not self._api_key:
            logger.warning("Cannot check rate limit: API key not configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openalex.org/rate-limit",
                    params={"api_key": self._api_key},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                rate_limit_info = data.get("rate_limit", {})
                credits_limit = rate_limit_info.get("credits_limit", 0)
                credits_used = rate_limit_info.get("credits_used", 0)
                credits_remaining = rate_limit_info.get("credits_remaining", 0)
                resets_in_seconds = rate_limit_info.get("resets_in_seconds", 0)
                resets_in_hours = math.ceil(resets_in_seconds / 3600)

                logger.info(
                    "📊 OpenAlex Rate Limit: %d/%d credits used, %d remaining (resets in %dh)",
                    credits_used,
                    credits_limit,
                    credits_remaining,
                    resets_in_hours,
                )

                return rate_limit_info
        except Exception as e:
            logger.error("Failed to check OpenAlex rate limit: %s", e)
            return None

    async def fetch_raw(
        self,
        query: str,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list:
        """Return raw OpenAlex works (list of dicts) for debugging/export."""
        try:
            works_query = Works().search_filter(title_and_abstract=query)
            if min_citations:
                works_query = works_query.filter(cited_by_count=f">{min_citations}")
            if date_from:
                works_query = works_query.filter(
                    from_publication_date=date_from.isoformat()
                )
            if date_to:
                works_query = works_query.filter(
                    to_publication_date=date_to.isoformat()
                )
            results = []
            for page in works_query.paginate(
                per_page=min(25, max_results), n_max=max_results
            ):
                results.extend(page)

            # Apply pyalex trick to reinvert abstracts
            for page in results:
                page["abstract"] = page["abstract"]

            return results
        except Exception as e:
            logger.error("OpenAlex raw fetch failed: %s", e)
            return []
