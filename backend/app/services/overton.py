import pandas as pd
from typing import Dict, Optional
from datetime import date
from app.utils.overton import OvertonClient
from app.core.config import settings


class OvertonService:
    def __init__(self):
        self.client = OvertonClient()

    async def search(
        self,
        query: str,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        source_country: Optional[str] = None,
        source_type: Optional[str] = None,
        published_after: Optional[date] = None,
        published_before: Optional[date] = None,
        topics: Optional[str] = None,
        classifications: Optional[str] = None,
        semantic_search: bool = True,
    ) -> pd.DataFrame:
        """Search Overton for policy documents using the Overton API"""

        # Build search parameters
        search_params = {
            ("squery" if semantic_search else "query"): query,
            "min_similarity": 0.3,
            "sort": "relevance",
        }

        # Add optional filters
        if source_country:
            # Simplified special region handling using frontend labels
            if source_country == "All":
                # Do not set any filter for 'All'
                pass
            elif source_country == "All but UK":
                search_params["source_country"] = "_:uxf"
            elif source_country == "UK":
                search_params["source_country"] = "UK"
            elif source_country in [
                "OECD members",
                "Non-OECD members",
                "G20",
                "G7",
                "North America",
                "South and Central America",
                "Europe",
                "Nordics",
                "APAC",
                "Africa",
            ]:
                # Pass frontend label directly as source_region
                search_params["source_region"] = source_country
            else:
                search_params["source_country"] = source_country
        if source_type:
            if source_type.strip() and source_type != "all":
                search_params["source_type"] = source_type
        if published_after:
            search_params["published_after"] = published_after.isoformat()
        if published_before:
            search_params["published_before"] = published_before.isoformat()
        if topics:
            search_params["topics"] = topics
        if classifications:
            search_params["classifications"] = classifications

        # Get results from Overton API using efficient pagination
        response = self.client.search_documents(
            max_results=max_results, fetch_mode="up_to_max", **search_params
        )

        # Handle response format (single response or list of responses)
        if isinstance(response, list):
            # Multiple pages - combine all results
            documents = []
            for page_response in response:
                documents.extend(page_response.get("results", []))
        else:
            # Single page response
            documents = response.get("results", [])

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

            # URLs and identifiers
            overton_url = doc.get("overton_url", "")
            document_url = doc.get("document_url", "")  # may be a PDF or a landing page
            pdf_url = doc.get("pdf_url") or (
                document_url
                if isinstance(document_url, str)
                and document_url.lower().endswith(".pdf")
                else ""
            )
            # Prefer document_url as landing page if it's not a direct PDF; otherwise fall back to Overton portal page
            landing_page_url = (
                document_url
                if isinstance(document_url, str)
                and not document_url.lower().endswith(".pdf")
                else overton_url
            )

            # DOI from keyed identifiers when available
            keyed_ids = doc.get("keyed_other_identifiers", {}) or {}
            doi_list = keyed_ids.get("doi") or []
            doi_value = (
                doi_list[0]
                if isinstance(doi_list, list) and len(doi_list) > 0
                else None
            )

            result = {
                "id": doc.get("policy_document_id", ""),
                "title": doc.get("title", ""),
                "abstract": content,
                "content": content[:1000]
                if content
                else "No content available",  # Limit to 1000 chars
                "authors": authors,
                "publication_date": doc.get("published_on", ""),
                "publication_year": int(doc.get("published_on", "").split("-")[0])
                if doc.get("published_on")
                and doc.get("published_on").split("-")[0].isdigit()
                else None,
                "venue": doc.get("source", {}).get("title", ""),
                "doi": doi_value or "",
                "cited_by_count": doc.get("citation_count", 0),
                "topics": topics_list,
                "source_country": doc.get("source", {}).get("country", ""),
                "source_type": doc.get("source", {}).get("type", ""),
                "published_on": doc.get("published_on", ""),
                "overton_url": overton_url,
                "document_url": document_url,
                "landing_page_url": landing_page_url,
                "pdf_url": pdf_url,
                "is_oa": None,
            }
            results.append(result)

        # Create DataFrame
        df = pd.DataFrame(results)

        # Clean up the data
        df["abstract"] = df["abstract"].fillna("No abstract available")
        df["content"] = df["content"].fillna("No content available")
        df["authors"] = df["authors"].apply(lambda x: x if isinstance(x, list) else [])

        return df

    async def fetch_raw(
        self,
        **kwargs,
    ):
        """Return raw Overton JSON (first page) for debugging/export."""
        try:
            return self.client.search_documents_raw(**kwargs)
        except Exception:
            return {}

    def format_for_screening(self, df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
        """Format policy documents for LLM screening"""
        # Create dictionary with title and content
        return df.set_index("id")[["title", "content"]].to_dict("index")
