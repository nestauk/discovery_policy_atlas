import pandas as pd
from typing import Optional
from datetime import date

try:
    import mediacloud.api
except ImportError:
    mediacloud = None
from app.core.config import settings

# Add these imports for scraping and LLM
try:
    from scrapling.fetchers import Fetcher
except ImportError:
    Fetcher = None
from app.utils.llm.llm_utils import get_llm

UK_COLLECTION_NAME = "United Kingdom - National"


def resolve_collection_id(api_key: str, collection_name: str) -> int:
    """
    Return the numerical collection_id that exactly matches `collection_name`.
    Raises ValueError if no match is found.
    """
    dir_api = mediacloud.api.DirectoryApi(api_key)
    # The Directory endpoint is paginated; we loop until a match is found
    offset = 0
    PAGE = 250  # tune as desired (max 500)
    while True:
        page = dir_api.collection_list(limit=PAGE, offset=offset)
        for coll in page["results"]:
            if coll["name"].lower() == collection_name.lower():
                return coll["id"]
        if page["next"] is None:  # no more pages
            break
        offset += PAGE
    raise ValueError(f"Collection '{collection_name}' not found")


class MediaCloudService:
    def __init__(self):
        api_key = settings.MEDIACLOUD_API_KEY
        if not api_key:
            raise ValueError("MEDIACLOUD_API_KEY not set in environment")
        if mediacloud is None:
            raise ImportError("mediacloud.api not installed")
        self.uk_collection_id = resolve_collection_id(api_key, UK_COLLECTION_NAME)
        self.api = mediacloud.api.SearchApi(api_key)
        # LLM config (adjust as needed)
        self.llm = get_llm(model_name="gpt-4o", temperature=0.2)

    def scrape_and_summarize(self, url: str) -> Optional[str]:
        """Fetch main text from URL and summarize it using LLM."""
        if not Fetcher:
            return None
        try:
            page = Fetcher.get(url, stealthy_headers=True)
            text = page.get_all_text(ignore_tags=("script", "style"))
            if not text or len(text) < 100:
                return None
            # Summarize with LLM
            prompt = f"Summarize the following news article in 2-3 sentences:\n\n{text[:4000]}"
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"Scraping/summarizing failed for {url}: {e}")
            return None

    async def search(
        self,
        query: str,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> pd.DataFrame:
        today = date.today()
        start_date = date_from or today
        end_date = date_to or today
        print(start_date)
        all_stories = []
        pagination_token = None
        while len(all_stories) < max_results:
            page, pagination_token = self.api.story_list(
                query, start_date, end_date, pagination_token=pagination_token
            )
            all_stories += page
            if not pagination_token or len(all_stories) >= max_results:
                break
        # Truncate to max_results
        all_stories = all_stories[:max_results]
        # Build DataFrame
        df = pd.DataFrame(all_stories)
        # Standardize columns
        df = df.rename(
            columns={
                "id": "id",
                "title": "title",
                "description": "abstract",
                "publish_date": "publish_date",
            }
        )
        if "abstract" not in df.columns:
            df["abstract"] = ""
        df["content"] = df["abstract"].fillna("")  # Use description as content

        # Go to each website and scrape the content
        if Fetcher is not None:
            for idx, row in df.iterrows():
                if (not row.get("abstract")) and row.get("url"):
                    summary = self.scrape_and_summarize(row["url"])
                    if summary:
                        df.at[idx, "abstract"] = summary
                        df.at[idx, "content"] = summary

        return df[["id", "title", "abstract", "content", "publish_date"]]

    def format_for_screening(self, df: pd.DataFrame):
        return df.set_index("id")[["title", "content"]].to_dict("index")
