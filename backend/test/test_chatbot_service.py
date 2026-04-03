"""Focused tests for high-value chatbot service behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chatbot.chat_service import ChatbotService
from app.services.chatbot.models import ChatRequest


@pytest.mark.asyncio
async def test_chat_compacts_and_filters_cited_references(monkeypatch):
    service = ChatbotService()
    first_hit = {
        "document_id": "doc-1",
        "chunk_index": 0,
        "chunk_type": "content",
        "content": "First evidence hit.",
        "document_title": "First Evidence Review",
        "document_authors": ["A. Researcher"],
        "document_doi": "10.1000/first",
        "document_overton_url": None,
        "document_published_date": "2024-01-01",
        "document_year": 2024,
    }
    second_hit = {
        "document_id": "doc-2",
        "chunk_index": 0,
        "chunk_type": "content",
        "content": "Second evidence hit.",
        "document_title": "Second Evidence Review",
        "document_authors": ["B. Researcher"],
        "document_doi": "10.1000/second",
        "document_overton_url": None,
        "document_published_date": "2023-01-01",
        "document_year": 2023,
    }
    third_hit = {
        "document_id": "doc-3",
        "chunk_index": 0,
        "chunk_type": "content",
        "content": "Third evidence hit.",
        "document_title": "Third Evidence Review",
        "document_authors": ["C. Researcher"],
        "document_doi": "10.1000/third",
        "document_overton_url": None,
        "document_published_date": "2022-01-01",
        "document_year": 2022,
    }
    fake_message = SimpleNamespace(
        content="The most relevant items are [Documents 1 and 3]."
    )

    async def _fake_run(messages, handlers):
        service._ordered_references = [
            service._build_document_reference(first_hit),
            service._build_document_reference(second_hit),
            service._build_document_reference(third_hit),
        ]
        return fake_message

    monkeypatch.setattr(service, "_run_agent_loop", _fake_run)

    response = await service.chat(
        "project-1",
        ChatRequest(message="What does the evidence say?"),
    )

    assert response.message == "The most relevant items are [1][2]."
    assert [ref.title for ref in response.references] == [
        "First Evidence Review",
        "Third Evidence Review",
    ]


@pytest.mark.asyncio
async def test_search_relevant_chunks_uses_project_title_in_query(monkeypatch):
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
