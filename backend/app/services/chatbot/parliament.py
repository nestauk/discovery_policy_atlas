"""UK Parliament API client for chatbot tool-calling."""

import asyncio
import logging
import re
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

HANSARD_SEARCH_URL = "https://hansard-api.parliament.uk/search.json"
PQS_SEARCH_URL = (
    "https://questions-statements-api.parliament.uk/api/writtenquestions/questions"
)
HANSARD_TIMEOUT = 15.0
HANSARD_MAX_RESULTS = 3
PARLIAMENT_FINAL_RESULTS = 3
PQS_MAX_RESULTS = 6
RERANK_EMBED_TEXT_MAX_CHARS = 4000

_STOPWORDS = frozenset(
    {
        "the",
        "of",
        "to",
        "in",
        "for",
        "and",
        "a",
        "an",
        "on",
        "is",
        "by",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "be",
        "as",
        "at",
        "or",
        "it",
        "its",
        "has",
        "have",
        "been",
        "being",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "not",
        "no",
        "but",
        "if",
        "so",
        "than",
        "too",
        "very",
        "about",
        "into",
        "through",
        "between",
        "after",
        "before",
        "during",
        "without",
        "within",
        "what",
        "which",
        "how",
    }
)

_GENERIC_TERMS = frozenset(
    {
        "interventions",
        "intervention",
        "impact",
        "impacts",
        "restrictions",
        "restriction",
        "consumption",
        "measures",
        "measure",
        "policies",
        "policy",
        "strategies",
        "strategy",
        "approaches",
        "approach",
        "outcomes",
        "outcome",
        "effects",
        "effect",
        "reduce",
        "reduction",
        "increase",
        "improve",
        "address",
        "related",
        "based",
    }
)


def _salience(word: str) -> int:
    """Score a word's distinctiveness for search query simplification."""
    score = len(word)
    if word.isupper() and len(word) >= 2:
        score += 20  # acronyms
    elif word[0].isupper():
        score += 5  # proper nouns
    if word.lower() in _GENERIC_TERMS:
        score -= 10
    return score


def _simplify_query(query: str) -> List[str]:
    """Generate progressively shorter query variants, preserving salient terms."""
    words = [w for w in query.split() if w.lower() not in _STOPWORDS]
    if len(words) <= 1:
        return []

    ranked = sorted(words, key=_salience, reverse=True)

    variants: List[str] = []
    for n in range(len(ranked) - 1, 0, -1):
        keep = set(ranked[:n])
        variant = " ".join(w for w in words if w in keep)
        if variant and variant not in variants:
            variants.append(variant)
    return variants


def _default_parliament_date_from(today: Optional[date] = None) -> str:
    """Return the default lower bound for Hansard searches: last 10 years."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - 10).isoformat()
    except ValueError:
        return today.replace(year=today.year - 10, day=28).isoformat()


def _default_parliamentary_questions_date_from(today: Optional[date] = None) -> str:
    """Return the default lower bound for written question searches: last 3 years."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - 3).isoformat()
    except ValueError:
        return today.replace(year=today.year - 3, day=28).isoformat()


def _normalise_whitespace(text: str) -> str:
    """Collapse internal whitespace while preserving plain text content."""
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate_text(text: str, limit: int) -> str:
    """Truncate text without breaking the UI with very long answer bodies."""
    text = _normalise_whitespace(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _iso_date(value: Any) -> str:
    """Return YYYY-MM-DD from an API date field."""
    if not value:
        return ""
    if isinstance(value, str):
        return value[:10]
    return str(value)[:10]


def _member_name(member: Any) -> str:
    """Extract a display name from a nested member object."""
    if not isinstance(member, dict):
        return ""
    return _normalise_whitespace(member.get("name") or member.get("listAs") or "")


def _parliamentary_question_url(
    question_id: Any,
    date_tabled: str,
    uin: str,
) -> str:
    """Build a user-facing parliamentary question detail URL."""
    if date_tabled and uin:
        return (
            "https://questions-statements.parliament.uk/"
            f"written-questions/detail/{date_tabled}/{uin}"
        )
    if question_id is not None:
        return f"{PQS_SEARCH_URL}/{question_id}"
    return PQS_SEARCH_URL


def _needs_question_enrichment(question: Dict[str, Any]) -> bool:
    """Detect truncated list payloads that need a follow-up detail fetch."""
    fields = (
        question.get("questionText"),
        question.get("answerText"),
        question.get("comparableAnswerText"),
        question.get("originalAnswerText"),
    )
    return any(
        isinstance(field, str) and field.rstrip().endswith("...") for field in fields
    )


def _has_substantive_answer(question: Dict[str, Any]) -> bool:
    """Filter to answered written questions with meaningful answer content."""
    answer_text = _normalise_whitespace(
        question.get("answerText")
        or question.get("comparableAnswerText")
        or question.get("originalAnswerText")
        or ""
    )
    if question.get("isWithdrawn"):
        return False
    if not question.get("dateAnswered"):
        return False
    if question.get("answerIsHolding"):
        return False
    if len(answer_text) < 25:
        return False

    lower_answer = answer_text.lower()
    if lower_answer.startswith("holding answer received"):
        return False

    return True


def _parse_parliamentary_question(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a written question API object into the chat item shape."""
    if not _has_substantive_answer(question):
        return None

    question_id = question.get("id")
    if question_id is None:
        return None

    uin = _normalise_whitespace(question.get("uin") or "")
    heading = _normalise_whitespace(question.get("heading") or "")
    answering_body = _normalise_whitespace(question.get("answeringBodyName") or "")
    asking_member = _member_name(question.get("askingMember"))
    answering_member = _member_name(question.get("answeringMember"))
    question_text = _normalise_whitespace(question.get("questionText") or "")
    answer_text = _normalise_whitespace(
        question.get("answerText")
        or question.get("comparableAnswerText")
        or question.get("originalAnswerText")
        or ""
    )
    date_tabled = _iso_date(question.get("dateTabled"))
    date_answered = _iso_date(question.get("dateAnswered")) or date_tabled

    title = heading or (
        f"Written Question {uin}" if uin else "Written Parliamentary Question"
    )
    if answering_body:
        title = f"{title} — {answering_body}"

    content_parts = []
    if answer_text:
        content_parts.append(f"Answer: {_truncate_text(answer_text, 500)}")
    if question_text:
        content_parts.append(f"Question: {_truncate_text(question_text, 220)}")

    rerank_parts = [
        heading,
        uin,
        asking_member,
        answering_member,
        answering_body,
        answer_text,
        question_text,
    ]

    return {
        "id": f"pq-{question_id}",
        "title": title,
        "date": date_answered,
        "content": " ".join(part for part in content_parts if part).strip(),
        "rerank_text": " ".join(part for part in rerank_parts if part).strip(),
        "source_type": "written_question",
        "source_label": "parliamentary_questions",
        "source_display": "UK Parliament Written Questions",
        "url": _parliamentary_question_url(question_id, date_tabled, uin),
    }


async def _fetch_full_parliamentary_question(
    client: httpx.AsyncClient, question_id: Any
) -> Optional[Dict[str, Any]]:
    """Fetch a full written question record when the list payload is truncated."""
    if question_id is None:
        return None

    response = await client.get(
        f"{PQS_SEARCH_URL}/{question_id}",
        params={"expandMember": True},
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return None

    value = data.get("value")
    return value if isinstance(value, dict) else None


async def _batch_embed(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts in a single OpenAI API call."""
    if not texts:
        return []

    from app.services.vectorization import vectorization_service as _vs

    client = _vs.openai_client
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=[t.replace("\n", " ") for t in texts],
    )
    return [d.embedding for d in response.data]


async def _rerank_items(
    original_query: str,
    items: List[Dict[str, Any]],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Rerank items by semantic similarity to the original query."""
    if len(items) <= 1:
        return items[:top_k]

    limit = min(top_k, len(items))

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [_truncate_text(original_query, RERANK_EMBED_TEXT_MAX_CHARS)] + [
            _truncate_text(
                (
                    f"{it['title']} | {it['source_type']} | {it['date']} | "
                    f"{it.get('rerank_text', it['content'])}"
                ),
                RERANK_EMBED_TEXT_MAX_CHARS,
            )
            for it in items
        ]
        embeddings = await _batch_embed(texts)
        query_emb = embeddings[0]
        item_embs = embeddings[1:]

        scores = cosine_similarity([query_emb], item_embs)[0]
        for i, item in enumerate(items):
            if item.get("pinned"):
                scores[i] += 0.1

        ranked = sorted(zip(scores, items), key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[:limit]]
    except Exception as exc:
        logger.warning("Reranking failed, returning first %d items: %s", limit, exc)
        return items[:limit]


def _ensure_source_diversity(
    ranked_items: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Keep at least one result from each source when both sources have hits."""
    if top_k < 2 or len(ranked_items) <= top_k:
        return ranked_items[:top_k]

    source_order = list(
        dict.fromkeys(
            item.get("source_label")
            for item in ranked_items
            if item.get("source_label")
        )
    )
    if len(source_order) <= 1:
        return ranked_items[:top_k]

    selected = list(ranked_items[:top_k])
    counts = Counter(item.get("source_label") for item in selected)
    selected_ids = {item.get("id") for item in selected if item.get("id")}

    for source_label in source_order:
        if counts[source_label] > 0:
            continue

        replacement = next(
            (
                item
                for item in ranked_items[top_k:]
                if item.get("source_label") == source_label
                and item.get("id") not in selected_ids
            ),
            None,
        )
        if replacement is None:
            continue

        replace_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if counts[selected[index].get("source_label")] > 1
            ),
            None,
        )
        if replace_index is None:
            continue

        previous = selected[replace_index]
        counts[previous.get("source_label")] -= 1
        if previous.get("id"):
            selected_ids.discard(previous["id"])

        selected[replace_index] = replacement
        counts[source_label] += 1
        if replacement.get("id"):
            selected_ids.add(replacement["id"])

    return selected[:top_k]


def _hansard_slug(text: str) -> str:
    """Convert a Hansard title/section to the path slug used on parliament.uk."""
    if not text:
        return ""
    parts = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _hansard_url(
    house: str,
    date: str,
    ext_id: str,
    source_type: str = "debate",
    slug_text: str = "",
    contribution_id: str = "",
) -> str:
    """Build a Hansard deep link for debates and contributions."""
    if not (house and date and ext_id):
        return ""

    slug = _hansard_slug(slug_text)
    if source_type == "debate" and slug:
        return f"https://hansard.parliament.uk/{house}/{date}/debates/{ext_id}/{slug}"
    if source_type == "contribution" and slug:
        url = f"https://hansard.parliament.uk/{house}/{date}/debates/{ext_id}/{slug}"
        if contribution_id:
            return f"{url}#contribution-{contribution_id}"
        return url
    if source_type == "written_statement":
        return f"https://hansard.parliament.uk/html/{house}/{date}/WrittenStatements"
    if source_type == "written_answer":
        return f"https://hansard.parliament.uk/html/{house}/{date}/WrittenAnswers"
    return ""


def _parse_contribution(
    raw: Dict[str, Any],
    source_type: str,
    title_prefix: str,
    fallback_url: str,
    seen_ids: set,
) -> Optional[Dict[str, Any]]:
    """Parse a contribution/statement/answer into a standard item dict."""
    member = raw.get("AttributedTo", raw.get("MemberName", "Unknown"))
    section = raw.get("DebateSection", "")
    item_date = raw.get("SittingDate", "")[:10]
    house = raw.get("House", "")
    text = raw.get("ContributionText", "")[:300]
    full_text = raw.get("ContributionTextFull", "")
    ext_id = raw.get("DebateSectionExtId", "")
    contrib_id = raw.get("ContributionExtId", "")
    url = (
        _hansard_url(
            house,
            item_date,
            ext_id,
            source_type,
            slug_text=section,
            contribution_id=contrib_id,
        )
        or fallback_url
    )

    item_id = f"{source_type[:6]}-{contrib_id or f'{item_date}-{member[:20]}'}"
    if item_id in seen_ids:
        return None
    seen_ids.add(item_id)

    title = (
        f"{member} — {title_prefix}{section}"
        if title_prefix
        else f"{member} — {section}"
    )
    return {
        "id": item_id,
        "title": title,
        "date": item_date,
        "content": text,
        "rerank_text": full_text or text,
        "source_type": source_type,
        "source_label": "hansard",
        "source_display": "UK Parliament Hansard",
        "url": url,
    }


def _fetch_hansard(
    data: Dict[str, Any],
    query: str,
    seen_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Parse a Hansard API response into a flat list of items."""
    if seen_ids is None:
        seen_ids = set()

    fallback_url = (
        f"https://hansard.parliament.uk/search?searchTerm={quote_plus(query)}"
    )
    items: List[Dict[str, Any]] = []

    for debate in data.get("Debates", []):
        title = debate.get("Title", "Untitled debate")
        house = debate.get("House", "")
        item_date = debate.get("SittingDate", "")[:10]
        section = debate.get("DebateSection", "")
        ext_id = debate.get("DebateSectionExtId", "")
        url = _hansard_url(house, item_date, ext_id, slug_text=title) or fallback_url

        item_id = f"debate-{ext_id or item_date}-{title[:30]}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        items.append(
            {
                "id": item_id,
                "title": f"{title} — {house} {section} debate",
                "date": item_date,
                "content": (
                    f"Parliamentary debate titled '{title}' in {house} ({section}) on "
                    f"{item_date}."
                ),
                "rerank_text": f"{title} {section} {house} debate",
                "source_type": "debate",
                "source_label": "hansard",
                "source_display": "UK Parliament Hansard",
                "url": url,
            }
        )

    section_configs = [
        ("Contributions", "contribution", ""),
        ("WrittenStatements", "written_statement", "Written Statement: "),
        ("WrittenAnswers", "written_answer", "Written Answer: "),
    ]
    for api_key, source_type, title_prefix in section_configs:
        for raw in data.get(api_key, []):
            item = _parse_contribution(
                raw, source_type, title_prefix, fallback_url, seen_ids
            )
            if item:
                items.append(item)

    return items


async def _search_hansard(
    query: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Search Hansard with query broadening while preserving the existing behavior."""
    original_query = query
    seen_ids: set = set()
    effective_date_from = date_from or _default_parliament_date_from()

    params: Dict[str, Any] = {"take": HANSARD_MAX_RESULTS}
    if effective_date_from:
        params["startDate"] = effective_date_from
    if date_to:
        params["endDate"] = date_to

    async def _run(
        active_client: httpx.AsyncClient
    ) -> Tuple[List[Dict[str, Any]], str]:
        effective_query = original_query
        params["searchTerm"] = query
        response = await active_client.get(HANSARD_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()

        items = _fetch_hansard(data, query, seen_ids)

        for item in items:
            item["pinned"] = True

        for variant in _simplify_query(original_query):
            params["searchTerm"] = variant
            response = await active_client.get(HANSARD_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()

            new_items = _fetch_hansard(data, variant, seen_ids)
            items.extend(new_items)
            if new_items and effective_query == original_query:
                effective_query = variant

        return items, effective_query

    if client is not None:
        return await _run(client)

    async with httpx.AsyncClient(timeout=HANSARD_TIMEOUT) as active_client:
        return await _run(active_client)


async def _search_parliamentary_questions(
    query: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Search answered written questions and normalize them into chat items."""
    effective_date_from = date_from or _default_parliamentary_questions_date_from()
    params: Dict[str, Any] = {
        "expandMember": True,
        "take": PQS_MAX_RESULTS,
        "skip": 0,
        "searchTerm": query,
    }
    if effective_date_from:
        params["answeredWhenFrom"] = effective_date_from
    if date_to:
        params["answeredWhenTo"] = date_to

    async def _run(active_client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        response = await active_client.get(PQS_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return []

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            return []

        seen_ids = set()
        items: List[Dict[str, Any]] = []

        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue
            question = raw_result.get("value")
            if not isinstance(question, dict):
                continue

            if _needs_question_enrichment(question):
                try:
                    full_question = await _fetch_full_parliamentary_question(
                        active_client,
                        question.get("id"),
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to enrich written question %s: %s",
                        question.get("id"),
                        exc,
                    )
                else:
                    if isinstance(full_question, dict):
                        question = full_question

            item = _parse_parliamentary_question(question)
            if item is None or item["id"] in seen_ids:
                continue

            seen_ids.add(item["id"])
            items.append(item)

        return items

    if client is not None:
        return await _run(client)

    async with httpx.AsyncClient(timeout=HANSARD_TIMEOUT) as active_client:
        return await _run(active_client)


async def _search_hansard_safe(
    client: httpx.AsyncClient,
    query: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """Run the Hansard branch without letting exceptions escape the outer search."""
    try:
        items, effective_query = await _search_hansard(
            query,
            date_from=date_from,
            date_to=date_to,
            client=client,
        )
        return items, effective_query, None
    except Exception as exc:
        logger.warning("Hansard search failed for query %r: %s", query, exc)
        return [], query, str(exc)


async def _search_parliamentary_questions_safe(
    client: httpx.AsyncClient,
    query: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Run written-question search with explicit timeout/error diagnostics."""
    try:
        items = await _search_parliamentary_questions(
            query,
            date_from=date_from,
            date_to=date_to,
            client=client,
        )
        return items, None
    except TimeoutError:
        timeout_error = (
            f"written question search timed out after {HANSARD_TIMEOUT:.0f}s"
        )
        logger.warning("Written question search timed out for query %r", query)
        return [], timeout_error
    except httpx.TimeoutException as exc:
        timeout_error = (
            f"written question search timed out after {HANSARD_TIMEOUT:.0f}s: {exc}"
        )
        logger.warning(
            "Written question search HTTP timeout for query %r: %s", query, exc
        )
        return [], timeout_error
    except Exception as exc:
        logger.warning(
            "Written question search failed for query %r (%s): %s",
            query,
            type(exc).__name__,
            exc,
        )
        return [], f"{type(exc).__name__}: {exc}"


def _format_parliament_items(
    items: List[Dict[str, Any]],
    start_index: int,
) -> str:
    """Format mixed parliament results into the existing document-style tool output."""
    parts = []
    for i, item in enumerate(items, start_index):
        part = f"\n--- DOCUMENT {i}: {item['title']} ---\n"
        part += (
            f"Source: {item.get('source_display', 'UK Parliament')} "
            f"({item['source_type']})\n"
        )
        part += f"Date: {item['date']}\n"
        part += f"\n[CONTENT]: {item['content']}\n"
        parts.append(part)
    return "\n".join(parts)


async def search_parliament(
    query: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    start_index: int = 1,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Search Hansard plus answered written questions and return merged chat results."""
    async with httpx.AsyncClient(timeout=HANSARD_TIMEOUT) as client:
        hansard_task = asyncio.create_task(
            _search_hansard_safe(client, query, date_from, date_to)
        )
        pq_task = asyncio.create_task(
            _search_parliamentary_questions_safe(client, query, date_from, date_to)
        )

        (
            (hansard_items, effective_query, hansard_error),
            (
                pq_items,
                pq_error,
            ),
        ) = await asyncio.gather(hansard_task, pq_task)

    if not hansard_items and not pq_items:
        errors = [error for error in (hansard_error, pq_error) if error]
        if errors:
            return f"Parliament search failed: {'; '.join(errors)}", []
        return "No parliamentary results found for this topic.", []

    merged_items = []
    seen_ids = set()
    for item in hansard_items + pq_items:
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)
        merged_items.append(item)

    ranked_items = await _rerank_items(
        query,
        merged_items,
        top_k=len(merged_items),
    )
    final_items = _ensure_source_diversity(
        ranked_items,
        top_k=PARLIAMENT_FINAL_RESULTS,
    )

    text = _format_parliament_items(final_items, start_index)

    extra_links = []
    if hansard_items:
        extra_links.append(
            "Full Hansard search: "
            f"https://hansard.parliament.uk/search?searchTerm={quote_plus(effective_query)}"
        )
    if pq_items:
        extra_links.append(
            "Written questions API search: "
            f"{PQS_SEARCH_URL}?searchTerm={quote_plus(query)}"
        )

    if extra_links:
        text = text + "\n" + "\n".join(extra_links)

    return text, final_items
