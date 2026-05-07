"""Focused tests for high-value chatbot service behavior."""

import asyncio
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

    async def _fake_run(_messages, handlers, **_kwargs):
        await handlers["search_project_evidence"](query="interventions")
        return SimpleNamespace(
            content="The most relevant items are [Documents 1 and 3].",
            tool_calls=None,
            response_id=None,
        )

    monkeypatch.setattr(
        service,
        "_search_relevant_chunks",
        AsyncMock(
            return_value=[
                {"document_id": "doc-1", "chunk_index": 0, "content": "First"},
                {"document_id": "doc-2", "chunk_index": 0, "content": "Second"},
                {"document_id": "doc-3", "chunk_index": 0, "content": "Third"},
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "_get_chunks_with_neighbors",
        AsyncMock(
            return_value=[
                {"document_id": "doc-1", "chunk_index": 0, "content": "First"},
                {"document_id": "doc-2", "chunk_index": 0, "content": "Second"},
                {"document_id": "doc-3", "chunk_index": 0, "content": "Third"},
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "_enrich_with_document_details",
        AsyncMock(return_value=[first_hit, second_hit, third_hit]),
    )
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
async def test_chat_uses_request_scoped_state_for_concurrent_turns(monkeypatch):
    service = ChatbotService()

    async def _fake_search_relevant_chunks(
        project_id: str, query: str, max_chunks: int = 10
    ):
        _ = (query, max_chunks)
        return [
            {
                "document_id": f"{project_id}-doc",
                "chunk_index": 0,
                "content": "evidence",
            }
        ]

    async def _fake_get_chunks_with_neighbors(project_id: str, chunks):
        _ = project_id
        return chunks

    async def _fake_enrich_with_document_details(chunks):
        doc_id = chunks[0]["document_id"]
        project_id = doc_id.replace("-doc", "")
        return [
            {
                "document_id": doc_id,
                "chunk_index": 0,
                "chunk_type": "content",
                "content": f"Evidence for {project_id}",
                "document_title": f"Evidence {project_id}",
                "document_authors": [project_id],
                "document_doi": None,
                "document_overton_url": None,
                "document_published_date": "2024-01-01",
                "document_year": 2024,
            }
        ]

    async def _fake_run(messages, handlers, **_kwargs):
        await handlers["search_project_evidence"](query=messages[-1]["content"])
        await asyncio.sleep(0)
        return SimpleNamespace(
            content="Scoped answer [1].",
            tool_calls=None,
            response_id=None,
        )

    monkeypatch.setattr(
        service, "_search_relevant_chunks", _fake_search_relevant_chunks
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", _fake_get_chunks_with_neighbors
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", _fake_enrich_with_document_details
    )
    monkeypatch.setattr(service, "_run_agent_loop", _fake_run)

    response_a, response_b = await asyncio.gather(
        service.chat("project-a", ChatRequest(message="project-a")),
        service.chat("project-b", ChatRequest(message="project-b")),
    )

    assert response_a.references[0].document_id == "project-a-doc"
    assert response_b.references[0].document_id == "project-b-doc"
    assert response_a.references[0].title == "Evidence project-a"
    assert response_b.references[0].title == "Evidence project-b"


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
