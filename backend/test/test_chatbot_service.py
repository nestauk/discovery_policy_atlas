"""Unit tests for the chatbot service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chatbot.chat_service import ChatbotService
from app.services.chatbot.models import ChatRequest


@pytest.mark.asyncio
async def test_chat_returns_grounded_answer_for_relevant_project(monkeypatch):
    service = ChatbotService()
    enriched_hit = {
        "document_id": "doc-1",
        "chunk_index": 0,
        "chunk_type": "content",
        "content": "Housing First reduced time spent homeless in multiple evaluations.",
        "document_title": "Housing First Outcomes Review",
        "document_authors": ["A. Researcher"],
        "document_doi": "10.1000/housing-first",
        "document_overton_url": None,
        "document_published_date": "2024-01-01",
        "document_year": 2024,
    }
    fake_message = SimpleNamespace(
        content=(
            "The evidence suggests Housing First improves housing stability "
            "and reduces time spent homeless [Document 1]."
        )
    )
    monkeypatch.setattr(
        service, "_run_agent_loop", AsyncMock(return_value=fake_message)
    )

    # Simulate the tool handler having stored evidence chunks
    async def _fake_run(messages, handlers):
        service._last_evidence_chunks = [enriched_hit]
        return fake_message

    monkeypatch.setattr(service, "_run_agent_loop", _fake_run)

    response = await service.chat(
        "project-1",
        ChatRequest(message="What does the evidence say about Housing First?"),
    )

    assert "Housing First improves housing stability" in response.message
    assert len(response.references) == 1
    assert response.references[0].title == "Housing First Outcomes Review"
    assert response.references[0].url == "https://doi.org/10.1000/housing-first"


@pytest.mark.asyncio
async def test_chat_returns_no_evidence_message_when_no_hits(monkeypatch):
    service = ChatbotService()
    fake_message = SimpleNamespace(
        content="I don't have any relevant evidence to answer that question."
    )
    monkeypatch.setattr(
        service, "_run_agent_loop", AsyncMock(return_value=fake_message)
    )

    response = await service.chat("project-1", ChatRequest(message="test"))

    assert response.references == []
    assert "don't have any relevant evidence" in response.message


@pytest.mark.asyncio
async def test_chat_propagates_agent_loop_errors(monkeypatch):
    service = ChatbotService()
    monkeypatch.setattr(
        service,
        "_run_agent_loop",
        AsyncMock(side_effect=RuntimeError("openai request failed")),
    )

    with pytest.raises(RuntimeError, match="openai request failed"):
        await service.chat("project-1", ChatRequest(message="test"))


@pytest.mark.asyncio
async def test_search_relevant_chunks_uses_strict_vector_search(monkeypatch):
    service = ChatbotService()
    search_similar_content = AsyncMock(return_value=[])
    fake_vectorization_service = SimpleNamespace(
        search_similar_content=search_similar_content
    )
    monkeypatch.setattr(
        service, "_get_project_title", AsyncMock(return_value="Housing interventions")
    )
    monkeypatch.setattr(
        "app.services.chatbot.chat_service.vectorization_service",
        fake_vectorization_service,
    )

    await service._search_relevant_chunks("project-1", "housing", max_chunks=7)

    search_similar_content.assert_awaited_once_with(
        query="Project: Housing interventions\nQuestion: housing",
        project_id="project-1",
        match_threshold=0.51,
        match_count=7,
        raise_on_error=True,
    )


@pytest.mark.asyncio
async def test_search_relevant_chunks_falls_back_to_raw_query_without_project_title(
    monkeypatch,
):
    service = ChatbotService()
    search_similar_content = AsyncMock(return_value=[])
    fake_vectorization_service = SimpleNamespace(
        search_similar_content=search_similar_content
    )
    monkeypatch.setattr(service, "_get_project_title", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.chatbot.chat_service.vectorization_service",
        fake_vectorization_service,
    )

    await service._search_relevant_chunks("project-1", "housing", max_chunks=3)

    search_similar_content.assert_awaited_once_with(
        query="housing",
        project_id="project-1",
        match_threshold=0.51,
        match_count=3,
        raise_on_error=True,
    )
