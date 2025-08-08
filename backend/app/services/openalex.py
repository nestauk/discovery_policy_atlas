from pyalex import Works, config
import pandas as pd
from typing import Dict, Optional
from datetime import date
from openai import AsyncOpenAI
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class OpenAlexService:
    def __init__(self):
        # Configure PyAlex
        if settings.OPENALEX_EMAIL:
            config.email = settings.OPENALEX_EMAIL
        config.max_retries = 3
        config.retry_backoff_factor = 0.5

        # Initialize OpenAI client for boolean query generation
        if settings.OPENAI_API_KEY:
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self._openai_client = None
            logger.warning(
                "OpenAI API key not configured - boolean query generation will be disabled"
            )

    async def generate_boolean_query(self, original_query: str) -> str:
        """Generate a boolean search query optimized for OpenAlex using OpenAI"""
        if not self._openai_client:
            logger.warning("OpenAI client not available, returning original query")
            return original_query

        system_prompt = """You are an expert at creating boolean search queries for academic literature databases like OpenAlex.

Given a research question, create an optimized boolean search query that will find the most relevant academic papers. Follow these guidelines:

1. Use AND, OR, NOT operators appropriately
2. Group related terms with parentheses
3. Include synonyms and related terms with OR
4. Use quotes for exact phrases when appropriate
5. Consider academic terminology and jargon
6. Focus on terms that would appear in titles and abstracts
7. Keep the query concise but comprehensive

Return ONLY the boolean query string, nothing else."""

        user_prompt = f"Original research question: {original_query}\n\nCreate an optimized boolean search query for academic literature:"

        try:
            response = await self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )

            boolean_query = response.choices[0].message.content.strip()
            logger.info(f"Generated boolean query: {boolean_query}")
            return boolean_query

        except Exception as e:
            logger.error(f"Error generating boolean query: {e}")
            return original_query

    async def search(
        self,
        query: str,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> pd.DataFrame:
        """Search OpenAlex for papers using PyAlex"""

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

        # Get results directly into DataFrame
        results = []
        for page in works_query.paginate(
            per_page=min(25, max_results), n_max=max_results
        ):
            results.extend(page)

        # Process results to extract all available metadata
        processed_results = []
        for i, page in enumerate(results):
            try:
                # Extract authors with proper null checks
                authors = []
                if page.get("authorships"):
                    for authorship in page["authorships"]:
                        if authorship and isinstance(authorship, dict):
                            author = authorship.get("author")
                            if author and isinstance(author, dict):
                                display_name = author.get("display_name")
                                if display_name:
                                    authors.append(display_name)

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

                # Extract citation count
                cited_by_count = page.get("cited_by_count", 0)

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
                    "work_type": work_type,
                    "source_country": "Academic",  # OpenAlex is academic literature
                    "source_type": "Academic Paper",
                }
                processed_results.append(processed_result)
            except Exception as e:
                logger.error(f"Error processing result {i}: {e}")
                logger.error(f"Problematic page data: {page}")
                continue

        df = pd.DataFrame(processed_results)

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
        df["work_type"] = df["work_type"].fillna("unknown")
        df["source_country"] = df["source_country"].fillna("Academic")
        df["source_type"] = df["source_type"].fillna("Academic Paper")

        return df

    async def search_for_agent(
        self,
        query: str,
        max_results: int = 20,
        focus_on_reviews: bool = True,
        min_citations: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Enhanced search for agent functionality with boolean query generation
        and focus on reviews and meta-studies
        """
        try:
            # Generate boolean query using OpenAI
            boolean_query = await self.generate_boolean_query(query)

            # Add review terms if focusing on reviews
            if focus_on_reviews:
                boolean_query = f'({boolean_query}) AND ("review" OR "meta analysis" OR "systematic" OR "metastudy")'
                logger.info("Enhanced query to prioritize reviews and meta-analyses")

            logger.info(f"Using boolean query for search: {boolean_query}")

            # Build query with PyAlex using the boolean query
            works_query = Works().search_filter(title_and_abstract=boolean_query)

            # Add filters for reviews and meta-studies if requested
            if focus_on_reviews:
                # Instead of filtering by type (which seems too restrictive),
                # enhance the boolean query to prioritize reviews and meta-analyses
                # The boolean query already includes these terms from OpenAI
                logger.info(
                    "Search optimized for review articles and meta-analyses via boolean query"
                )

            # Add other filters
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

            # Sort by citation count for highest impact reviews
            # Note: PyAlex sort format is different - use .sort() method without sort param
            works_query = works_query.sort(cited_by_count="desc")

            # Get results directly into DataFrame
            results = []
            for page in works_query.paginate(
                per_page=min(25, max_results), n_max=max_results
            ):
                results.extend(page)

            if not results:
                logger.warning("No results found for OpenAlex search")
                return pd.DataFrame()

            logger.info(f"Retrieved {len(results)} results from OpenAlex")

            # Process results similar to the original search method
            processed_results = []
            for i, page in enumerate(results):
                try:
                    # Extract authors with proper null checks
                    authors = []
                    if page.get("authorships"):
                        for authorship in page["authorships"]:
                            if authorship and isinstance(authorship, dict):
                                author = authorship.get("author")
                                if author and isinstance(author, dict):
                                    display_name = author.get("display_name")
                                    if display_name:
                                        authors.append(display_name)

                    # Extract publication date
                    publication_date = None
                    if page.get("publication_date"):
                        publication_date = page["publication_date"]
                        logger.debug(f"Found publication_date: {publication_date}")
                    elif page.get("publication_year"):
                        publication_date = f"{page['publication_year']}-01-01"
                        logger.debug(
                            f"Found publication_year: {page['publication_year']}"
                        )
                    else:
                        logger.debug(
                            f"No publication date/year found for paper: {page.get('title', 'Unknown')}"
                        )

                    # Extract venue/journal information with proper null checks
                    venue = ""
                    primary_location = page.get("primary_location")
                    if primary_location and isinstance(primary_location, dict):
                        source = primary_location.get("source")
                        if source and isinstance(source, dict):
                            display_name = source.get("display_name")
                            if display_name:
                                venue = display_name

                    # Extract citation count
                    cited_by_count = page.get("cited_by_count", 0)

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
                        "work_type": work_type,
                        "source_country": "Academic",  # OpenAlex is academic literature
                        "source_type": "Academic Paper",
                    }
                    logger.debug(
                        f"Processed result - Year: {processed_result['publication_year']}, Date: {processed_result['publication_date']}"
                    )
                    processed_results.append(processed_result)
                except Exception as e:
                    logger.error(f"Error processing result {i}: {e}")
                    logger.error(f"Problematic page data: {page}")
                    continue

            df = pd.DataFrame(processed_results)

            # Clean up the data and handle NaN values
            df["abstract"] = df["abstract"].fillna("No abstract available")
            df["content"] = df["abstract"].str[
                :1000
            ]  # Limit content to first 1000 chars
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
            df["work_type"] = df["work_type"].fillna("unknown")
            df["source_country"] = df["source_country"].fillna("Academic")
            df["source_type"] = df["source_type"].fillna("Academic Paper")

            logger.info(f"OpenAlex search returned {len(df)} results")
            return df

        except Exception as e:
            logger.error(f"Error in OpenAlex agent search: {e}")
            # Return empty DataFrame on error
            return pd.DataFrame()

    def format_for_screening(self, df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
        """Format papers for LLM screening"""
        # Create dictionary with title and content
        return df.set_index("id")[["title", "content"]].to_dict("index")
