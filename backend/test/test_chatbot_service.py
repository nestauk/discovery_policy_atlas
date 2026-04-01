"""Unit tests for the chatbot service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chatbot.chat_service import ChatbotService
from app.services.chatbot.models import ChatRequest


@pytest.mark.asyncio
async def test_chat_returns_grounded_answer_for_relevant_project(monkeypatch):
    service = ChatbotService()
    retrieval_hit = {
        "document_id": "doc-1",
        "chunk_index": 0,
        "content": "Housing First reduced time spent homeless in multiple evaluations.",
    }
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
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        "The evidence suggests Housing First improves housing stability "
                        "and reduces time spent homeless [Document 1]."
                    )
                )
            )
        ]
    )
    fake_openai_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_response))
        )
    )

    service._openai_client = fake_openai_client
    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=[retrieval_hit])
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=[retrieval_hit])
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=[enriched_hit])
    )

    response = await service.chat(
        "project-1",
        ChatRequest(message="What does the evidence say about Housing First?"),
    )

    assert "Housing First improves housing stability" in response.message
    assert len(response.references) == 1
    assert response.references[0].title == "Housing First Outcomes Review"
    assert response.references[0].url == "https://doi.org/10.1000/housing-first"


@pytest.mark.asyncio
async def test_chat_returns_no_evidence_message_when_retrieval_has_no_hits(monkeypatch):
    service = ChatbotService()
    monkeypatch.setattr(service, "_search_relevant_chunks", AsyncMock(return_value=[]))

    response = await service.chat("project-1", ChatRequest(message="test"))

    assert response.references == []
    assert response.message.startswith("I don't have any relevant evidence")


@pytest.mark.asyncio
async def test_chat_propagates_retrieval_errors(monkeypatch):
    service = ChatbotService()
    monkeypatch.setattr(
        service,
        "_search_relevant_chunks",
        AsyncMock(side_effect=RuntimeError("vector search unavailable")),
    )

    with pytest.raises(RuntimeError, match="vector search unavailable"):
        await service.chat("project-1", ChatRequest(message="test"))


@pytest.mark.asyncio
async def test_chat_propagates_generation_errors(monkeypatch):
    service = ChatbotService()
    retrieval_hit = {"document_id": "doc-1", "content": "Relevant chunk"}
    enriched_hit = {
        "document_id": "doc-1",
        "content": "Relevant chunk",
        "document_title": "Doc 1",
    }

    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=[retrieval_hit])
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=[retrieval_hit])
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=[enriched_hit])
    )
    monkeypatch.setattr(service, "_build_context", lambda chunks: "context")
    monkeypatch.setattr(
        service,
        "_generate_response",
        AsyncMock(side_effect=RuntimeError("openai request failed")),
    )

    with pytest.raises(RuntimeError, match="openai request failed"):
        await service.chat("project-1", ChatRequest(message="What works?"))


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
