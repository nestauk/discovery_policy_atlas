"""Lean behavioural tests for chatbot tool-calling and parliament search."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.chatbot.parliament import search_parliament


def _make_text_response(content: str = "Here is my answer."):
    """Build a plain-text fake chat completion response."""
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _make_tool_call_response(tool_name: str, arguments: dict, call_id: str = "call_1"):
    """Build a fake chat completion response that requests one tool call."""
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=tool_name,
            arguments=json.dumps(arguments),
        ),
    )
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_search_parliament_returns_formatted_results():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "TotalDebates": 1,
        "TotalContributions": 1,
        "TotalWrittenStatements": 0,
        "Debates": [
            {
                "Title": "Housing Policy Debate",
                "House": "Commons",
                "DebateSection": "Westminster Hall",
                "SittingDate": "2025-03-15T00:00:00",
                "DebateSectionExtId": "ABC-123",
            },
        ],
        "Contributions": [
            {
                "MemberName": "Jane Smith",
                "AttributedTo": "Jane Smith (Lab)",
                "DebateSection": "Homelessness Report",
                "SittingDate": "2025-02-10T00:00:00",
                "ContributionText": "This is an important policy issue.",
            },
        ],
        "WrittenStatements": [],
    }

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("housing policy")

    assert "Housing Policy Debate" in text
    assert "Homelessness Report" in text
    assert "2025-03-15" in text
    assert len(items) == 2
    assert [item["source_type"] for item in items] == ["debate", "contribution"]


@pytest.mark.asyncio
async def test_search_parliament_no_results():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "TotalDebates": 0,
        "TotalContributions": 0,
        "TotalWrittenStatements": 0,
        "Debates": [],
        "Contributions": [],
        "WrittenStatements": [],
    }

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("obscure topic xyz")

    assert "No parliamentary results found" in text
    assert items == []


@pytest.mark.asyncio
async def test_search_parliament_api_error():
    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("housing")

    assert "Parliament search failed" in text
    assert items == []


@pytest.mark.asyncio
async def test_search_parliament_passes_date_filters():
    from app.services.chatbot.parliament import HANSARD_SEARCH_URL, PQS_SEARCH_URL

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "TotalDebates": 0,
        "TotalContributions": 0,
        "TotalWrittenStatements": 0,
        "Debates": [],
        "Contributions": [],
        "WrittenStatements": [],
    }

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await search_parliament("housing", date_from="2024-01-01", date_to="2024-06-30")

    hansard_call = next(
        call
        for call in mock_client.get.call_args_list
        if call.args[0] == HANSARD_SEARCH_URL
    )
    hansard_params = hansard_call.kwargs.get(
        "params", hansard_call.args[1] if len(hansard_call.args) > 1 else {}
    )
    pq_call = next(
        call
        for call in mock_client.get.call_args_list
        if call.args[0] == PQS_SEARCH_URL
    )
    pq_params = pq_call.kwargs.get(
        "params", pq_call.args[1] if len(pq_call.args) > 1 else {}
    )

    assert hansard_params.get("startDate") == "2024-01-01"
    assert hansard_params.get("endDate") == "2024-06-30"
    assert pq_params.get("answeredWhenFrom") == "2024-01-01"
    assert pq_params.get("answeredWhenTo") == "2024-06-30"


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_and_loops():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response("search_project_evidence", {"query": "housing"}),
            _make_text_response("Based on the evidence..."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    mock_handler = AsyncMock(return_value="Evidence about housing found.")

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "Tell me about housing"}],
        tool_handlers={"search_project_evidence": mock_handler},
    )

    assert result.content == "Based on the evidence..."
    assert fake_create.await_count == 2
    mock_handler.assert_awaited_once_with(query="housing")


@pytest.mark.asyncio
async def test_agent_loop_retries_with_tool_choice_none_after_empty_final_turn():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response("search_project_evidence", {"query": "housing"}),
            _make_text_response(""),
            _make_text_response("Grounded answer [1]."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    mock_handler = AsyncMock(return_value="Evidence about housing found.")

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "Tell me about housing"}],
        tool_handlers={"search_project_evidence": mock_handler},
    )

    assert result.content == "Grounded answer [1]."
    assert fake_create.await_count == 3
    assert fake_create.await_args_list[-1].kwargs["tool_choice"] == "none"


@pytest.mark.asyncio
async def test_agent_loop_can_call_get_project_synthesis(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response("get_project_synthesis", {}),
            _make_text_response("Here is the project synthesis."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    mock_get_synthesis = AsyncMock(return_value="HEADLINE\nUseful synthesis text.")
    monkeypatch.setattr(service, "_get_project_synthesis", mock_get_synthesis)

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "What works overall?"}],
        tool_handlers=service._build_tool_handlers("proj-1"),
    )

    assert result.content == "Here is the project synthesis."
    mock_get_synthesis.assert_awaited_once_with("proj-1")


@pytest.mark.asyncio
async def test_chat_full_loop_with_evidence_tool(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService
    from app.services.chatbot.models import ChatRequest

    service = ChatbotService()
    fake_chunks = [{"document_id": "doc-1", "chunk_index": 0, "content": "Evidence."}]
    enriched = [
        {
            **fake_chunks[0],
            "chunk_type": "content",
            "document_title": "Housing Report",
            "document_authors": ["Smith"],
            "document_doi": "10.1000/test",
            "document_overton_url": None,
            "document_published_date": "2024-01-01",
            "document_year": 2024,
        }
    ]

    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=enriched)
    )

    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response("search_project_evidence", {"query": "housing"}),
            _make_text_response("Housing First shows positive outcomes [1]."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    response = await service.chat(
        "proj-1", ChatRequest(message="What works for housing?")
    )

    assert "Housing First shows positive outcomes" in response.message
    assert len(response.references) == 1
    assert response.references[0].title == "Housing Report"
    assert fake_create.await_count == 2


@pytest.mark.asyncio
async def test_chat_full_loop_with_both_tools(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService
    from app.services.chatbot.models import ChatRequest

    service = ChatbotService()
    fake_chunks = [{"document_id": "doc-1", "chunk_index": 0, "content": "Evidence."}]
    enriched = [{**fake_chunks[0], "chunk_type": "content", "document_title": "Report"}]

    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=enriched)
    )
    monkeypatch.setattr(
        "app.services.chatbot.chat_service.search_parliament",
        AsyncMock(
            return_value=(
                "unused",
                [
                    {
                        "id": "h-1",
                        "title": "Housing Debate",
                        "date": "2025-03-15",
                        "content": "Parliamentary debate on housing.",
                        "source_type": "debate",
                        "url": "https://hansard.parliament.uk/debate/1",
                    }
                ],
            )
        ),
    )

    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response(
                "search_project_evidence", {"query": "housing"}, "call_1"
            ),
            _make_tool_call_response(
                "search_parliament", {"query": "housing policy"}, "call_2"
            ),
            _make_text_response("Combining evidence and parliamentary records..."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    response = await service.chat(
        "proj-1", ChatRequest(message="Housing policy feasibility?")
    )

    assert "Combining evidence and parliamentary records" in response.message
    assert fake_create.await_count == 3
    assert response.references == []


@pytest.mark.asyncio
async def test_chat_handles_tool_error_gracefully(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService
    from app.services.chatbot.models import ChatRequest

    service = ChatbotService()
    monkeypatch.setattr(
        service,
        "_search_relevant_chunks",
        AsyncMock(side_effect=RuntimeError("DB down")),
    )

    fake_create = AsyncMock(
        side_effect=[
            _make_tool_call_response("search_project_evidence", {"query": "test"}),
            _make_text_response("I encountered an error searching the evidence."),
        ]
    )
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    response = await service.chat("proj-1", ChatRequest(message="test"))

    assert "error" in response.message.lower()
    assert response.references == []
