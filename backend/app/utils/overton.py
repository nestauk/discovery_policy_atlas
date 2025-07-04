from urllib.parse import urlencode
import requests
from typing import Literal
from app.core.config import settings

# from app.models import PolicyDocument


class OvertonClient:
    def __init__(
        self,
        base_url: str = "https://app.overton.io/documents.php",
        api_key: str | None = settings.OVERTON_API_KEY,
    ):
        self.base_url = base_url
        self.api_key = api_key

        if api_key is None:
            msg = "api_key must be provided"
            raise ValueError(msg)

    def search_documents(
        self,
        query: str = None,
        squery: str = None,
        min_similarity: float = 0.3,
        max_results: int = None,
        fetch_mode: Literal["first_page", "all_pages", "up_to_max"] = "first_page",
        **kwargs,
    ):
        """
        Search for documents using the Overton API with flexible pagination options.

        Args:
            query (str): The search query string.
            squery (str): The semantic search query string.
            min_similarity (float): The minimum similarity threshold (default is 0.3).
            max_results (int): Maximum number of results to return. Used with fetch_mode="up_to_max".
            fetch_mode (str): Pagination mode:
                - "first_page": Return only first page (default)
                - "all_pages": Fetch all available pages
                - "up_to_max": Fetch pages until max_results is reached
            **kwargs: Additional parameters for the search (e.g., year, source_country, sort).

        Returns:
            dict: The JSON response from the API. For multi-page results, returns a list of responses.
        """
        params = {
            "min_similarity": min_similarity,
            "format": "json",
            "api_key": self.api_key,
        }
        if query is not None:
            params["query"] = query
        if squery is not None:
            params["squery"] = squery
        params.update(kwargs)

        # For first_page mode, return single response
        if fetch_mode == "first_page":
            url = f"{self.base_url}?{urlencode(params, safe='|')}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()

        # For multi-page modes, collect all responses
        responses = []
        current_url = f"{self.base_url}?{urlencode(params, safe='|')}"
        total_results = 0

        while current_url:
            response = requests.get(current_url, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            responses.append(response_data)

            # Count results in current page
            current_results = len(response_data.get("results", []))
            total_results += current_results

            # Check if we should continue fetching
            if fetch_mode == "up_to_max" and max_results is not None:
                if total_results >= max_results:
                    # We have enough results, stop fetching
                    break

            # Get next page URL
            next_page_url = response_data.get("query", {}).get("next_page_url")
            if next_page_url is False or next_page_url is None:
                # No more pages available
                break
            current_url = next_page_url

        # For single response, return the response directly
        if len(responses) == 1:
            return responses[0]

        # For multiple responses, return the list
        return responses

    # Legacy methods for backward compatibility
    def search_all_documents(self, min_similarity: float = 0.3, **kwargs):
        """
        Legacy method: Search for all documents using the Overton API.
        Use search_documents with fetch_mode="all_pages" instead.
        """
        return self.search_documents(
            min_similarity=min_similarity, fetch_mode="all_pages", **kwargs
        )
