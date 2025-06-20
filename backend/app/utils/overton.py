from urllib.parse import urlencode
import requests
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
        **kwargs,
    ):
        """
        Search for documents using the Overton API.

        Args:
            query (str): The search query string.
            squery (str): The semantic search query string.
            min_similarity (float): The minimum similarity threshold (default is 0.3).
            **kwargs: Additional parameters for the search (e.g., year, source_country, sort).

        Returns:
            dict: The JSON response from the API.
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
        url = f"{self.base_url}?{urlencode(params, safe='|')}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        return response.json()

    def search_all_documents(self, min_similarity: float = 0.3, **kwargs):
        """
        Search for all documents using the Overton API.

        Args:
            min_similarity (float): The minimum similarity threshold (default is 0.3).
            **kwargs: Additional parameters for the search (e.g., year, source_country, sort).

        Returns:
            dict: The JSON response from the API.
        """
        responses = []

        params = {
            # "squery": None,
            "min_similarity": min_similarity,
            "format": "json",
            "api_key": self.api_key,
            "sort": "relevance",
        }
        params.update(kwargs)
        url = f"{self.base_url}?{urlencode(params, safe='|')}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        responses.append(response.json())
        while response.json()["query"]["next_page_url"] is not False:
            url = response.json()["query"]["next_page_url"]
            response = requests.get(url)
            response.raise_for_status()
            responses.append(response.json())
        return responses

    # def get_document(self, doc_id: str):
    #     """
    #     Get a document by its ID using the Overton API.

    #     Args:
    #         doc_id (str): The document ID.

    #     Returns:
    #         dict: The JSON response from the API.
    #     """
    #     params = {
    #         "policy_document_id": doc_id,
    #         "format": "json",
    #         "api_key": self.api_key,
    #     }
    #     url = f"{self.base_url}?{urlencode(params, safe='|')}"
    #     response = requests.get(url, timeout=30)
    #     response.raise_for_status()
    #     response = response.json()

    #     policy_docs = []
    #     for result in response["results"]:
    #         try:
    #             policy_docs.append(PolicyDocument(**result))
    #         except ValidationError as err:
    #             print("Invalid document:", err)
    #     return policy_docs[0]
