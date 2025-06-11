from pyalex import Works, config
import pandas as pd
from typing import Dict, Optional
from datetime import date
from app.core.config import settings


class OpenAlexService:
    def __init__(self):
        # Configure PyAlex
        if settings.OPENALEX_EMAIL:
            config.email = settings.OPENALEX_EMAIL
        config.max_retries = 3
        config.retry_backoff_factor = 0.5

    async def search(
        self,
        query: str,
        max_results: int = 10,
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

        for page in results:
            page["abstract"] = page["abstract"]

        # Create DataFrame with only needed columns
        df = pd.DataFrame(results)[["id", "title", "abstract"]]

        # Clean up the data
        df["abstract"] = df["abstract"].fillna("No abstract available")
        df["content"] = df["abstract"].str[:1000]  # Limit content to first 1000 chars

        return df

    def format_for_screening(self, df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
        """Format papers for LLM screening"""
        # Create dictionary with title and content
        return df.set_index("id")[["title", "content"]].to_dict("index")
