"""Tests for chatbot tool-calling: Parliament API, tool definitions, agent loop."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.chatbot.parliament import search_parliament


# ---------------------------------------------------------------------------
# Step 1: Parliament API client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parliament_returns_formatted_results():
    fake_json = {
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
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = fake_json

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("housing policy")

    assert "Housing Policy Debate" in text
    assert "Commons" in text
    assert "2025-03-15" in text
    assert "Jane Smith" in text
    assert "Homelessness Report" in text
    assert len(items) == 2
    assert items[0]["source_type"] == "debate"
    assert items[1]["source_type"] == "contribution"
    assert items[0]["url"] is not None


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

    # Should return an error message, not raise
    assert isinstance(text, str)
    assert "Parliament search failed" in text
    assert items == []


@pytest.mark.asyncio
async def test_search_parliament_passes_date_filters():
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

    call_kwargs = mock_client.get.call_args
    params = call_kwargs.kwargs.get(
        "params", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
    )
    assert params.get("startDate") == "2024-01-01"
    assert params.get("endDate") == "2024-06-30"


@pytest.mark.asyncio
async def test_search_parliament_defaults_to_last_10_years(monkeypatch):
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

    monkeypatch.setattr(
        "app.services.chatbot.parliament._default_parliament_date_from",
        lambda today=None: "2016-04-02",
    )

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await search_parliament("housing")

    call_kwargs = mock_client.get.call_args
    params = call_kwargs.kwargs.get(
        "params", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
    )
    assert params.get("startDate") == "2016-04-02"
    assert "endDate" not in params


# ---------------------------------------------------------------------------
# Step 2: Tool definitions
# ---------------------------------------------------------------------------


def test_tool_definitions_have_required_openai_fields():
    from app.services.chatbot.chat_service import TOOL_DEFINITIONS

    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert fn["parameters"]["type"] == "object"


def test_tool_definitions_contain_expected_tools():
    from app.services.chatbot.chat_service import TOOL_DEFINITIONS

    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert names == {"search_project_evidence", "search_parliament"}


# ---------------------------------------------------------------------------
# Step 3: Agent loop
# ---------------------------------------------------------------------------


def _make_text_response(content="Here is my answer."):
    """Helper: fake OpenAI response with plain text (no tool calls)."""
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _make_tool_call_response(tool_name, arguments_dict, call_id="call_1"):
    """Helper: fake OpenAI response requesting a tool call."""
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=tool_name,
            arguments=json.dumps(arguments_dict),
        ),
    )
    msg = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.mark.asyncio
async def test_agent_loop_returns_text_when_no_tool_calls():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    fake_create = AsyncMock(return_value=_make_text_response("The answer is 42."))
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "What is 42?"}],
        tool_handlers={},
    )

    assert result.content == "The answer is 42."
    fake_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_and_loops():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    tool_response = _make_tool_call_response(
        "search_project_evidence", {"query": "housing"}
    )
    text_response = _make_text_response("Based on the evidence...")
    fake_create = AsyncMock(side_effect=[tool_response, text_response])
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    mock_handler = AsyncMock(return_value="Evidence about housing found.")
    handlers = {"search_project_evidence": mock_handler}

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "Tell me about housing"}],
        tool_handlers=handlers,
    )

    assert result.content == "Based on the evidence..."
    assert fake_create.await_count == 2
    mock_handler.assert_awaited_once_with(query="housing")


@pytest.mark.asyncio
async def test_agent_loop_stops_after_max_iterations():
    from app.services.chatbot.chat_service import ChatbotService, MAX_AGENT_ITERATIONS

    service = ChatbotService()
    # Always return tool calls
    tool_response = _make_tool_call_response("search_project_evidence", {"query": "x"})
    fake_create = AsyncMock(return_value=tool_response)
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    mock_handler = AsyncMock(return_value="some evidence")
    handlers = {"search_project_evidence": mock_handler}

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "test"}],
        tool_handlers=handlers,
    )

    assert fake_create.await_count == MAX_AGENT_ITERATIONS
    # Should return a message even after hitting the cap
    assert result is not None


@pytest.mark.asyncio
async def test_agent_loop_handles_unknown_tool():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    unknown_tool_response = _make_tool_call_response("nonexistent_tool", {})
    text_response = _make_text_response("I couldn't find that tool.")
    fake_create = AsyncMock(side_effect=[unknown_tool_response, text_response])
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "test"}],
        tool_handlers={},
    )

    assert fake_create.await_count == 2
    assert result.content == "I couldn't find that tool."


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_execution_error():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    tool_response = _make_tool_call_response(
        "search_project_evidence", {"query": "test"}
    )
    text_response = _make_text_response("Sorry, I encountered an error.")
    fake_create = AsyncMock(side_effect=[tool_response, text_response])
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    failing_handler = AsyncMock(side_effect=RuntimeError("DB connection lost"))
    handlers = {"search_project_evidence": failing_handler}

    result = await service._run_agent_loop(
        messages=[{"role": "user", "content": "test"}],
        tool_handlers=handlers,
    )

    assert fake_create.await_count == 2
    assert result.content == "Sorry, I encountered an error."


# ---------------------------------------------------------------------------
# Step 4: Tool handler builder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_tool_handlers_returns_both_tools():
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    handlers = service._build_tool_handlers("proj-1")
    assert "search_project_evidence" in handlers
    assert "search_parliament" in handlers
    assert callable(handlers["search_project_evidence"])
    assert callable(handlers["search_parliament"])


@pytest.mark.asyncio
async def test_search_project_evidence_handler_calls_rag_pipeline(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    service._last_evidence_chunks = []

    fake_chunks = [{"document_id": "doc-1", "chunk_index": 0, "content": "Evidence."}]
    enriched = [{**fake_chunks[0], "document_title": "Doc Title"}]

    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=enriched)
    )

    handlers = service._build_tool_handlers("proj-1")
    result = await handlers["search_project_evidence"](query="housing")

    service._search_relevant_chunks.assert_awaited_once_with("proj-1", "housing")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_search_project_evidence_handler_no_results(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    service._last_evidence_chunks = []
    monkeypatch.setattr(service, "_search_relevant_chunks", AsyncMock(return_value=[]))

    handlers = service._build_tool_handlers("proj-1")
    result = await handlers["search_project_evidence"](query="obscure topic")

    assert "No relevant evidence found" in result


@pytest.mark.asyncio
async def test_search_project_evidence_handler_stores_chunks(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    service._last_evidence_chunks = []

    fake_chunks = [{"document_id": "doc-1", "chunk_index": 0, "content": "Evidence."}]
    enriched = [{**fake_chunks[0], "document_title": "Doc Title"}]

    monkeypatch.setattr(
        service, "_search_relevant_chunks", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_get_chunks_with_neighbors", AsyncMock(return_value=fake_chunks)
    )
    monkeypatch.setattr(
        service, "_enrich_with_document_details", AsyncMock(return_value=enriched)
    )

    handlers = service._build_tool_handlers("proj-1")
    await handlers["search_project_evidence"](query="housing")

    assert service._last_evidence_chunks == enriched


# ---------------------------------------------------------------------------
# Step 5: Stable [Document N] numbering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_handlers_keep_document_numbers_stable_across_calls(monkeypatch):
    from app.services.chatbot.chat_service import ChatbotService

    service = ChatbotService()
    service._last_evidence_chunks = []
    service._last_parliament_items = []

    first_chunks = [{"document_id": "doc-1", "chunk_index": 0, "content": "Evidence A"}]
    second_chunks = [
        {"document_id": "doc-1", "chunk_index": 0, "content": "Evidence A"},
        {"document_id": "doc-2", "chunk_index": 0, "content": "Evidence B"},
    ]
    first_enriched = [{**first_chunks[0], "document_title": "Housing Report"}]
    second_enriched = [
        {**second_chunks[0], "document_title": "Housing Report"},
        {**second_chunks[1], "document_title": "Support Package"},
    ]
    parliament_items = [
        {
            "id": "h-1",
            "title": "Housing Debate",
            "date": "2025-03-15",
            "content": "Parliament discussed housing.",
            "source_type": "debate",
            "url": "https://hansard.parliament.uk/debate/1",
        }
    ]

    monkeypatch.setattr(
        service,
        "_search_relevant_chunks",
        AsyncMock(side_effect=[first_chunks, second_chunks]),
    )
    monkeypatch.setattr(
        service,
        "_get_chunks_with_neighbors",
        AsyncMock(side_effect=[first_chunks, second_chunks]),
    )
    monkeypatch.setattr(
        service,
        "_enrich_with_document_details",
        AsyncMock(side_effect=[first_enriched, second_enriched]),
    )
    monkeypatch.setattr(
        "app.services.chatbot.chat_service.search_parliament",
        AsyncMock(return_value=("unused", parliament_items)),
    )

    handlers = service._build_tool_handlers("proj-1")

    first_evidence = await handlers["search_project_evidence"](query="housing")
    parliament = await handlers["search_parliament"](query="housing")
    second_evidence = await handlers["search_project_evidence"](query="support")

    assert "--- DOCUMENT 1: Housing Report ---" in first_evidence
    assert "--- DOCUMENT 2: Housing Debate ---" in parliament
    assert "--- DOCUMENT 1: Housing Report ---" in second_evidence
    assert "--- DOCUMENT 3: Support Package ---" in second_evidence
    assert [ref.title for ref in service._get_ordered_references()] == [
        "Housing Report",
        "Housing Debate",
        "Support Package",
    ]


# ---------------------------------------------------------------------------
# Step 8: Integration tests — full chat() through agent loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_full_loop_with_evidence_tool(monkeypatch):
    """End-to-end: chat() → agent loop → evidence tool → final response."""
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

    # First call: model requests evidence tool. Second call: model returns text.
    tool_call_resp = _make_tool_call_response(
        "search_project_evidence", {"query": "housing"}
    )
    text_resp = _make_text_response(
        "Housing First shows positive outcomes [Document 1]."
    )
    fake_create = AsyncMock(side_effect=[tool_call_resp, text_resp])
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
    """End-to-end: model calls both evidence and parliament tools."""
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

    # Mock parliament tool at module level
    mock_parliament = AsyncMock(
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
    )
    monkeypatch.setattr(
        "app.services.chatbot.chat_service.search_parliament", mock_parliament
    )

    # Three calls: evidence tool, parliament tool, then text
    evidence_resp = _make_tool_call_response(
        "search_project_evidence", {"query": "housing"}, "call_1"
    )
    parliament_resp = _make_tool_call_response(
        "search_parliament", {"query": "housing policy"}, "call_2"
    )
    text_resp = _make_text_response("Combining evidence and parliamentary records...")
    fake_create = AsyncMock(side_effect=[evidence_resp, parliament_resp, text_resp])
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    response = await service.chat(
        "proj-1", ChatRequest(message="Housing policy feasibility?")
    )

    assert "Combining evidence and parliamentary records" in response.message
    assert fake_create.await_count == 3
    mock_parliament.assert_awaited_once_with(query="housing policy")
    assert [ref.title for ref in response.references] == ["Report", "Housing Debate"]


@pytest.mark.asyncio
async def test_chat_handles_tool_error_gracefully(monkeypatch):
    """If the evidence tool raises, the model still gets an error string and responds."""
    from app.services.chatbot.chat_service import ChatbotService
    from app.services.chatbot.models import ChatRequest

    service = ChatbotService()

    monkeypatch.setattr(
        service,
        "_search_relevant_chunks",
        AsyncMock(side_effect=RuntimeError("DB down")),
    )

    tool_call_resp = _make_tool_call_response(
        "search_project_evidence", {"query": "test"}
    )
    text_resp = _make_text_response("I encountered an error searching the evidence.")
    fake_create = AsyncMock(side_effect=[tool_call_resp, text_resp])
    service._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    response = await service.chat("proj-1", ChatRequest(message="test"))

    assert "error" in response.message.lower()
    assert response.references == []


# ---------------------------------------------------------------------------
# Query broadening: _simplify_query
# ---------------------------------------------------------------------------


def test_simplify_query_preserves_acronyms():
    from app.services.chatbot.parliament import _simplify_query

    variants = _simplify_query("interventions to reduce consumption of HFSS foods")
    assert len(variants) >= 1
    assert all("HFSS" in v for v in variants)


def test_simplify_query_single_word():
    from app.services.chatbot.parliament import _simplify_query

    assert _simplify_query("HFSS") == []


def test_simplify_query_drops_stopwords():
    from app.services.chatbot.parliament import _simplify_query

    variants = _simplify_query(
        "the impact of food advertising restrictions on children"
    )
    assert len(variants) >= 1
    for v in variants:
        words = v.lower().split()
        assert "the" not in words
        assert "of" not in words
        assert "on" not in words


def test_simplify_query_penalizes_generic_terms():
    from app.services.chatbot.parliament import _simplify_query

    # "interventions" alone should never be the sole variant when "HFSS" is available
    variants = _simplify_query("interventions to reduce consumption of HFSS foods")
    single_word_variants = [v for v in variants if len(v.split()) == 1]
    if single_word_variants:
        assert single_word_variants[-1] == "HFSS"


def test_simplify_query_preserves_original_order():
    from app.services.chatbot.parliament import _simplify_query

    original = "UK sugar tax impact on childhood obesity"
    original_words = original.split()
    variants = _simplify_query(original)
    for v in variants:
        v_words = v.split()
        # Check each word appears in the same relative order as in original
        indices = []
        for w in v_words:
            for i, ow in enumerate(original_words):
                if ow == w and i not in indices:
                    indices.append(i)
                    break
        assert indices == sorted(indices), f"Variant '{v}' not in original order"


def test_simplify_query_policy_examples():
    from app.services.chatbot.parliament import _simplify_query

    v1 = _simplify_query("interventions to reduce consumption of HFSS foods")
    assert any("HFSS" in v and "foods" in v for v in v1)

    v2 = _simplify_query("UK sugar tax impact on childhood obesity")
    assert any("sugar" in v.lower() and "obesity" in v.lower() for v in v2)


# ---------------------------------------------------------------------------
# Batch embedding helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_embed_returns_correct_count(monkeypatch):
    from app.services.chatbot.parliament import _batch_embed

    fake_embeddings = [
        SimpleNamespace(embedding=[0.1, 0.2]),
        SimpleNamespace(embedding=[0.3, 0.4]),
        SimpleNamespace(embedding=[0.5, 0.6]),
    ]
    fake_response = SimpleNamespace(data=fake_embeddings)
    fake_create = AsyncMock(return_value=fake_response)

    fake_client = SimpleNamespace(embeddings=SimpleNamespace(create=fake_create))
    fake_vs = SimpleNamespace(openai_client=fake_client)
    monkeypatch.setattr("app.services.vectorization.vectorization_service", fake_vs)

    result = await _batch_embed(["text1", "text2", "text3"])
    assert len(result) == 3
    assert result[0] == [0.1, 0.2]
    fake_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_embed_empty_input():
    from app.services.chatbot.parliament import _batch_embed

    result = await _batch_embed([])
    assert result == []


# ---------------------------------------------------------------------------
# Reranker: _rerank_items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_items_sorts_by_similarity(monkeypatch):
    from app.services.chatbot.parliament import _rerank_items

    # query=[1,0,0], B=[0,1,0] (dissimilar), C=[0,0,1] (dissimilar), A=[0.9,0.1,0] (similar)
    async def fake_batch_embed(texts):
        return [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.9, 0.1, 0]]

    monkeypatch.setattr(
        "app.services.chatbot.parliament._batch_embed", fake_batch_embed
    )

    items = [
        {
            "title": "B",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "irrelevant",
        },
        {
            "title": "C",
            "source_type": "debate",
            "date": "2025-01-02",
            "content": "also irrelevant",
        },
        {
            "title": "A",
            "source_type": "contribution",
            "date": "2025-02-01",
            "content": "relevant",
        },
    ]
    result = await _rerank_items("HFSS interventions", items, top_k=2)
    assert result[0]["title"] == "A"  # most similar to query


@pytest.mark.asyncio
async def test_rerank_items_respects_top_k(monkeypatch):
    from app.services.chatbot.parliament import _rerank_items

    async def fake_batch_embed(texts):
        return [[1, 0, 0]] * len(texts)

    monkeypatch.setattr(
        "app.services.chatbot.parliament._batch_embed", fake_batch_embed
    )

    items = [
        {
            "title": f"Item {i}",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "x",
        }
        for i in range(5)
    ]
    result = await _rerank_items("query", items, top_k=2)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_rerank_items_fallback_on_error(monkeypatch):
    from app.services.chatbot.parliament import _rerank_items

    async def failing_embed(texts):
        raise RuntimeError("API down")

    monkeypatch.setattr("app.services.chatbot.parliament._batch_embed", failing_embed)

    items = [
        {
            "title": f"Item {i}",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "x",
        }
        for i in range(5)
    ]
    result = await _rerank_items("query", items, top_k=3)
    assert len(result) == 3
    assert result == items[:3]


@pytest.mark.asyncio
async def test_rerank_items_boosts_pinned(monkeypatch):
    from app.services.chatbot.parliament import _rerank_items

    # query=[1,0,0], pinned=[0.5,0.5,0] (score~0.7), unpinned=[0.6,0.4,0] (score~0.8), filler=[0,0,1]
    # Without boost, unpinned wins. With +0.1 boost, pinned (~0.81) > unpinned (~0.83)...
    # Need tighter margin: pinned=[0.55,0.45,0] (~0.77+0.1=0.87), unpinned=[0.6,0.4,0] (~0.83)
    async def fake_batch_embed(texts):
        return [[1, 0, 0], [0.55, 0.45, 0], [0.6, 0.4, 0], [0, 0, 1]]

    monkeypatch.setattr(
        "app.services.chatbot.parliament._batch_embed", fake_batch_embed
    )

    items = [
        {
            "title": "Pinned",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "x",
            "pinned": True,
        },
        {
            "title": "Unpinned",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "x",
        },
        {
            "title": "Filler",
            "source_type": "debate",
            "date": "2025-01-01",
            "content": "x",
        },
    ]
    result = await _rerank_items("query", items, top_k=1)
    assert result[0]["title"] == "Pinned"


# ---------------------------------------------------------------------------
# _fetch_hansard helper + WrittenAnswers
# ---------------------------------------------------------------------------


def test_hansard_url_builds_debate_deeplink():
    from app.services.chatbot.parliament import _hansard_url

    url = _hansard_url(
        "Commons",
        "2025-11-05",
        "F0B22762-095C-40BC-B7DD-0513A6EF61C7",
        source_type="debate",
        slug_text="Fresh and Nutritious Food: Inequality of Access",
    )

    assert (
        url
        == "https://hansard.parliament.uk/Commons/2025-11-05/debates/F0B22762-095C-40BC-B7DD-0513A6EF61C7/FreshAndNutritiousFoodInequalityOfAccess"
    )


def test_hansard_url_builds_contribution_deeplink_with_anchor():
    from app.services.chatbot.parliament import _hansard_url

    url = _hansard_url(
        "Commons",
        "2025-11-05",
        "F0B22762-095C-40BC-B7DD-0513A6EF61C7",
        source_type="contribution",
        slug_text="Fresh and Nutritious Food: Inequality of Access",
        contribution_id="61E87A2D-EB54-4C91-9BB0-32D709F509F3",
    )

    assert (
        url
        == "https://hansard.parliament.uk/Commons/2025-11-05/debates/F0B22762-095C-40BC-B7DD-0513A6EF61C7/FreshAndNutritiousFoodInequalityOfAccess#contribution-61E87A2D-EB54-4C91-9BB0-32D709F509F3"
    )


def test_hansard_url_builds_written_answer_day_page():
    from app.services.chatbot.parliament import _hansard_url

    url = _hansard_url(
        "Commons",
        "2009-03-12",
        "09031289000036",
        source_type="written_answer",
        slug_text="Nutrition: Children",
        contribution_id="09031289000751",
    )

    assert url == "https://hansard.parliament.uk/html/Commons/2009-03-12/WrittenAnswers"


def test_hansard_url_builds_written_statement_day_page():
    from app.services.chatbot.parliament import _hansard_url

    url = _hansard_url(
        "Commons",
        "2021-06-24",
        "A344703D-53C7-48F9-A0FE-6DD2AA17A594",
        source_type="written_statement",
        slug_text="High Fat, Sugar and Salt Advertising Consultation Response",
        contribution_id="A344703D-53C7-48F9-A0FE-6DD2AA17A594",
    )

    assert (
        url == "https://hansard.parliament.uk/html/Commons/2021-06-24/WrittenStatements"
    )


def _make_hansard_response(
    debates=None, contributions=None, written_statements=None, written_answers=None
):
    """Helper: build a fake Hansard API response dict."""
    return {
        "TotalDebates": len(debates or []),
        "TotalContributions": len(contributions or []),
        "TotalWrittenStatements": len(written_statements or []),
        "TotalWrittenAnswers": len(written_answers or []),
        "Debates": debates or [],
        "Contributions": contributions or [],
        "WrittenStatements": written_statements or [],
        "WrittenAnswers": written_answers or [],
    }


@pytest.mark.asyncio
async def test_fetch_hansard_parses_all_sections():
    from app.services.chatbot.parliament import _fetch_hansard

    data = _make_hansard_response(
        debates=[
            {
                "Title": "D1",
                "House": "Commons",
                "SittingDate": "2025-01-01T00:00:00",
                "DebateSection": "Main",
                "DebateSectionExtId": "ext1",
            }
        ],
        contributions=[
            {
                "AttributedTo": "MP1 (Lab)",
                "DebateSection": "D1",
                "SittingDate": "2025-01-02T00:00:00",
                "ContributionText": "Short",
                "ContributionTextFull": "Full text here",
                "ContributionExtId": "c1",
                "DebateSectionExtId": "ext1",
                "House": "Commons",
            }
        ],
        written_statements=[
            {
                "AttributedTo": "Minister (Con)",
                "DebateSection": "S1",
                "SittingDate": "2025-01-03T00:00:00",
                "ContributionText": "Stmt short",
                "ContributionTextFull": "Stmt full text",
                "ContributionExtId": "s1",
                "DebateSectionExtId": "ext2",
                "House": "Commons",
            }
        ],
        written_answers=[
            {
                "AttributedTo": "SecState (Lab)",
                "DebateSection": "WA1",
                "SittingDate": "2025-01-04T00:00:00",
                "ContributionText": "Answer short",
                "ContributionTextFull": "Answer full text",
                "ContributionExtId": "wa1",
                "DebateSectionExtId": "ext3",
                "House": "Commons",
            }
        ],
    )
    items = _fetch_hansard(data, "test query")
    types = {it["source_type"] for it in items}
    assert types == {"debate", "contribution", "written_statement", "written_answer"}
    assert len(items) == 4
    assert items[0]["url"].endswith("/debates/ext1/D1")
    assert (
        items[1]["url"]
        == "https://hansard.parliament.uk/Commons/2025-01-02/debates/ext1/D1#contribution-c1"
    )
    assert (
        items[2]["url"]
        == "https://hansard.parliament.uk/html/Commons/2025-01-03/WrittenStatements"
    )
    assert (
        items[3]["url"]
        == "https://hansard.parliament.uk/html/Commons/2025-01-04/WrittenAnswers"
    )


@pytest.mark.asyncio
async def test_fetch_hansard_uses_full_text_for_rerank():
    from app.services.chatbot.parliament import _fetch_hansard

    data = _make_hansard_response(
        contributions=[
            {
                "AttributedTo": "MP1",
                "DebateSection": "D1",
                "SittingDate": "2025-01-01T00:00:00",
                "ContributionText": "Short snippet",
                "ContributionTextFull": "This is the much longer full text for reranking purposes",
                "ContributionExtId": "c1",
                "DebateSectionExtId": "ext1",
                "House": "Commons",
            }
        ],
    )
    items = _fetch_hansard(data, "test")
    assert (
        items[0]["rerank_text"]
        == "This is the much longer full text for reranking purposes"
    )


@pytest.mark.asyncio
async def test_fetch_hansard_deduplicates():
    from app.services.chatbot.parliament import _fetch_hansard

    contrib = {
        "AttributedTo": "MP1",
        "DebateSection": "D1",
        "SittingDate": "2025-01-01T00:00:00",
        "ContributionText": "Text",
        "ContributionTextFull": "Full",
        "ContributionExtId": "same-id",
        "DebateSectionExtId": "ext1",
        "House": "Commons",
    }
    data = _make_hansard_response(contributions=[contrib, contrib])
    items = _fetch_hansard(data, "test")
    assert len(items) == 1


# ---------------------------------------------------------------------------
# search_parliament: broadening, reranking, pinning, dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parliament_broadens_on_empty(monkeypatch):
    from app.services.chatbot.parliament import search_parliament

    call_log = []

    def fake_fetch(data, query, seen_ids=None):
        call_log.append(query)
        if "interventions" in query:
            return []  # original too specific
        return [
            {
                "id": "c1",
                "title": "Result",
                "date": "2025-01-01",
                "content": "x",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "x",
            },
            {
                "id": "c2",
                "title": "Result2",
                "date": "2025-01-02",
                "content": "y",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "y",
            },
            {
                "id": "c3",
                "title": "Result3",
                "date": "2025-01-03",
                "content": "z",
                "source_type": "debate",
                "url": "http://h",
                "rerank_text": "z",
            },
        ]

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = _make_hansard_response()

    async def fake_rerank(query, items, top_k=3):
        return items[:top_k]

    monkeypatch.setattr("app.services.chatbot.parliament._fetch_hansard", fake_fetch)
    monkeypatch.setattr("app.services.chatbot.parliament._rerank_items", fake_rerank)

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament(
            "interventions to reduce HFSS foods",
            date_from="2024-01-01",
        )

    assert len(items) > 0
    assert len(call_log) > 1  # broadened at least once


@pytest.mark.asyncio
async def test_search_parliament_always_broadens_and_merges(monkeypatch):
    from app.services.chatbot.parliament import search_parliament

    call_log = []
    call_counter = [0]

    def fake_fetch(data, query, seen_ids=None):
        call_log.append(query)
        call_counter[0] += 1
        idx = call_counter[0]
        return [
            {
                "id": f"c{idx}",
                "title": f"R{idx}",
                "date": "2025-01-01",
                "content": "x",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "x",
            }
        ]

    async def fake_rerank(query, items, top_k=3):
        return items[:top_k]

    monkeypatch.setattr("app.services.chatbot.parliament._fetch_hansard", fake_fetch)
    monkeypatch.setattr("app.services.chatbot.parliament._rerank_items", fake_rerank)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = _make_hansard_response()

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("HFSS foods")

    # Always broadens even when original query has results
    assert len(call_log) > 1


@pytest.mark.asyncio
async def test_search_parliament_pins_original_hits(monkeypatch):
    from app.services.chatbot.parliament import search_parliament

    captured_items = []

    def fake_fetch(data, query, seen_ids=None):
        return [
            {
                "id": "c1",
                "title": "Original",
                "date": "2025-01-01",
                "content": "x",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "x",
            },
        ]

    async def fake_rerank(query, items, top_k=3):
        captured_items.extend(items)
        return items[:top_k]

    monkeypatch.setattr("app.services.chatbot.parliament._fetch_hansard", fake_fetch)
    monkeypatch.setattr("app.services.chatbot.parliament._rerank_items", fake_rerank)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = _make_hansard_response()

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # This will broaden because only 1 result
        text, items = await search_parliament("specific HFSS query")

    # Items from original query should be pinned
    pinned = [it for it in captured_items if it.get("pinned")]
    assert len(pinned) >= 1
    assert pinned[0]["title"] == "Original"


@pytest.mark.asyncio
async def test_search_parliament_fallback_url_uses_effective_query(monkeypatch):
    from app.services.chatbot.parliament import search_parliament

    def fake_fetch(data, query, seen_ids=None):
        if "specific" in query:
            return []
        return [
            {
                "id": f"c{i}",
                "title": f"R{i}",
                "date": "2025-01-01",
                "content": "x",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "x",
            }
            for i in range(3)
        ]

    async def fake_rerank(query, items, top_k=3):
        return items[:top_k]

    monkeypatch.setattr("app.services.chatbot.parliament._fetch_hansard", fake_fetch)
    monkeypatch.setattr("app.services.chatbot.parliament._rerank_items", fake_rerank)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = _make_hansard_response()

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("specific HFSS query")

    # URL should contain the broadened term, not "specific"
    assert (
        "specific" not in text.split("searchTerm=")[-1].split("&")[0]
        if "searchTerm=" in text
        else True
    )


@pytest.mark.asyncio
async def test_search_parliament_deduplicates_across_queries(monkeypatch):
    from app.services.chatbot.parliament import search_parliament

    call_count = [0]

    def fake_fetch(data, query, seen_ids=None):
        call_count[0] += 1
        # Both calls return item with same id
        items = [
            {
                "id": "same-id",
                "title": "Shared",
                "date": "2025-01-01",
                "content": "x",
                "source_type": "contribution",
                "url": "http://h",
                "rerank_text": "x",
            },
        ]
        if seen_ids is not None:
            items = [it for it in items if it["id"] not in seen_ids]
            for it in items:
                seen_ids.add(it["id"])
        return items

    async def fake_rerank(query, items, top_k=3):
        return items[:top_k]

    monkeypatch.setattr("app.services.chatbot.parliament._fetch_hansard", fake_fetch)
    monkeypatch.setattr("app.services.chatbot.parliament._rerank_items", fake_rerank)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = _make_hansard_response()

    with patch("app.services.chatbot.parliament.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        text, items = await search_parliament("specific HFSS query")

    # Even with broadening, the duplicate should appear only once
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids))
