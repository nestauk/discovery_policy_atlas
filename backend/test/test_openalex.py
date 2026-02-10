"""Integration tests for OpenAlex API service."""

import pytest
import pandas as pd

from app.services.openalex import OpenAlexService, sanitize_openalex_query
from app.core.config import settings


class TestSanitizeOpenAlexQuery:
    """Tests for query sanitization function."""

    def test_removes_commas_inside_quotes(self):
        query = '"climate change, adaptation" OR "global warming"'
        result = sanitize_openalex_query(query)
        assert result == '"climate change adaptation" OR "global warming"'

    def test_preserves_commas_outside_quotes(self):
        query = "climate, change, adaptation"
        result = sanitize_openalex_query(query)
        assert result == "climate, change, adaptation"

    def test_handles_empty_string(self):
        result = sanitize_openalex_query("")
        assert result == ""

    def test_handles_no_quotes(self):
        query = "climate change adaptation"
        result = sanitize_openalex_query(query)
        assert result == "climate change adaptation"


@pytest.mark.skipif(
    not settings.OPENALEX_API_KEY, reason="OPENALEX_API_KEY not configured"
)
class TestOpenAlexServiceIntegration:
    """Integration tests that make real API calls to OpenAlex."""

    @pytest.fixture
    def service(self):
        return OpenAlexService()

    @pytest.mark.asyncio
    async def test_search_returns_results(self, service):
        """Test that search returns a DataFrame with expected columns."""
        df = await service.search(
            query="machine learning",
            max_results=10,
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) <= 10
        assert len(df) > 0

        expected_columns = ["id", "title", "abstract", "doi", "authors"]
        for col in expected_columns:
            assert col in df.columns, f"Missing column: {col}"

    @pytest.mark.asyncio
    async def test_search_with_return_total(self, service):
        """Test that search can return total count."""
        df, total = await service.search(
            query="climate change",
            max_results=5,
            return_n_total=True,
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) <= 5
        assert isinstance(total, int)
        assert total > 0

    @pytest.mark.asyncio
    async def test_search_minimal_returns_limited_fields(self, service):
        """Test that minimal search returns only essential fields."""
        df = await service.search_minimal(
            query="renewable energy",
            max_results=10,
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) <= 10

        expected_columns = ["id", "doi", "title", "cited_by_count", "relevance_score"]
        assert list(df.columns) == expected_columns

    @pytest.mark.asyncio
    async def test_search_minimal_count_only(self, service):
        """Test that count_only returns just an integer."""
        count = await service.search_minimal(
            query="artificial intelligence",
            count_only=True,
        )

        assert isinstance(count, int)
        assert count > 0

    @pytest.mark.asyncio
    async def test_check_rate_limit(self, service):
        """Test that rate limit check returns expected structure."""
        rate_limit = await service.check_rate_limit()

        assert rate_limit is not None
        assert "credits_limit" in rate_limit
        assert "credits_used" in rate_limit
        assert "credits_remaining" in rate_limit
        assert "resets_in_seconds" in rate_limit

        assert isinstance(rate_limit["credits_limit"], int)
        assert rate_limit["credits_limit"] > 0
        assert rate_limit["credits_remaining"] >= 0


@pytest.mark.skipif(
    settings.OPENALEX_API_KEY is not None,
    reason="Test only runs when API key is NOT configured",
)
class TestOpenAlexServiceWithoutApiKey:
    """Tests for behavior when API key is not configured."""

    @pytest.fixture
    def service(self):
        return OpenAlexService()

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_none(self, service):
        """Test that rate limit check returns None without API key."""
        result = await service.check_rate_limit()
        assert result is None
