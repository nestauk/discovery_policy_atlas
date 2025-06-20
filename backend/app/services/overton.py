import pandas as pd
from typing import Dict, Optional
from datetime import date
from app.utils.overton import OvertonClient


class OvertonService:
    def __init__(self):
        self.client = OvertonClient()

    async def search(
        self,
        query: str,
        max_results: int = 10,
        source_country: Optional[str] = None,
        source_type: Optional[str] = None,
        published_after: Optional[date] = None,
        published_before: Optional[date] = None,
        topics: Optional[str] = None,
        classifications: Optional[str] = None,
    ) -> pd.DataFrame:
        """Search Overton for policy documents using the Overton API"""

        # Build search parameters
        search_params = {
            "query": query,
            "min_similarity": 0.3,
            "sort": "relevance",
        }

        # Add optional filters
        if source_country:
            search_params["source_country"] = source_country
        if source_type:
            search_params["source_type"] = source_type
        if published_after:
            search_params["published_after"] = published_after.isoformat()
        if published_before:
            search_params["published_before"] = published_before.isoformat()
        if topics:
            search_params["topics"] = topics
        if classifications:
            search_params["classifications"] = classifications

        # Get results from Overton API
        response = self.client.search_documents(**search_params)

        # Extract documents from response
        documents = response.get("results", [])

        # Limit results to max_results
        documents = documents[: min(max_results, len(documents))]

        # Convert to DataFrame
        results = []
        for doc in documents:
            # Extract authors - handle both string and list formats
            authors = doc.get("authors", [])
            if isinstance(authors, str):
                authors = [authors] if authors else []

            # Extract topics - handle both string and list formats
            topics_list = doc.get("topics", [])
            if isinstance(topics_list, str):
                topics_list = [topics_list] if topics_list else []

            # Create content from snippet and description
            content_parts = []
            if doc.get("snippet"):
                content_parts.append(doc["snippet"])
            if doc.get("llm_document_description"):
                content_parts.append(doc["llm_document_description"])
            content = " ".join(content_parts)

            result = {
                "id": doc.get("policy_document_id", ""),
                "title": doc.get("title", ""),
                "abstract": content,
                "content": content[:1000]
                if content
                else "No content available",  # Limit to 1000 chars
                "authors": authors,
                "publication_year": doc.get("published_on", "").split("-")[0]
                if doc.get("published_on")
                else "",
                "venue": doc.get("source", {}).get("title", ""),
                "doi": doc.get("document_url", ""),
                "citation_count": doc.get("citation_count", 0),
                "topics": topics_list,
                "source_country": doc.get("source", {}).get("country", ""),
                "source_type": doc.get("source", {}).get("type", ""),
                "published_on": doc.get("published_on", ""),
                "overton_url": doc.get("overton_url", ""),
            }
            results.append(result)

        # Create DataFrame
        df = pd.DataFrame(results)

        # Clean up the data
        df["abstract"] = df["abstract"].fillna("No abstract available")
        df["content"] = df["content"].fillna("No content available")
        df["authors"] = df["authors"].apply(lambda x: x if isinstance(x, list) else [])

        return df

    def format_for_screening(self, df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
        """Format policy documents for LLM screening"""
        # Create dictionary with title and content
        return df.set_index("id")[["title", "content"]].to_dict("index")
