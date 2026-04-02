"""UK Parliament Hansard API client for chatbot tool-calling."""

import logging
import re
import sys
from datetime import date
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

HANSARD_SEARCH_URL = "https://hansard-api.parliament.uk/search.json"
HANSARD_TIMEOUT = 10.0
HANSARD_MAX_RESULTS = 3
HANSARD_MIN_RESULTS = 3

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
    """Generate progressively shorter query variants, preserving salient terms.

    - Strips stopwords
    - Scores remaining words (acronyms > proper nouns > long words > generic)
    - Emits variants in original word order
    """
    words = [w for w in query.split() if w.lower() not in _STOPWORDS]
    if len(words) <= 1:
        return []

    # Rank by salience to decide which words to keep
    ranked = sorted(words, key=_salience, reverse=True)

    variants: List[str] = []
    for n in range(len(ranked) - 1, 0, -1):
        keep = set(ranked[:n])
        # Emit in original word order
        variant = " ".join(w for w in words if w in keep)
        if variant and variant not in variants:
            variants.append(variant)
    return variants


def _default_parliament_date_from(today: Optional[date] = None) -> str:
    """Return the default lower bound for parliament searches: last 10 years."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - 10).isoformat()
    except ValueError:
        # Handle leap day when the target year is not a leap year.
        return today.replace(year=today.year - 10, day=28).isoformat()


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
    """Rerank items by semantic similarity to the original query.

    Pinned items (from the original query) get a score boost.
    Falls back to truncation on error.
    """
    if len(items) <= top_k:
        return items
    try:
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [original_query] + [
            f"{it['title']} | {it['source_type']} | {it['date']} | {it.get('rerank_text', it['content'])}"
            for it in items
        ]
        # Use module-level lookup so monkeypatching works in tests
        _this = sys.modules[__name__]
        embeddings = await _this._batch_embed(texts)
        query_emb = embeddings[0]
        item_embs = embeddings[1:]

        scores = cosine_similarity([query_emb], item_embs)[0]
        for i, item in enumerate(items):
            if item.get("pinned"):
                scores[i] += 0.1

        ranked = sorted(zip(scores, items), key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[:top_k]]
    except Exception as exc:
        logger.warning("Reranking failed, returning first %d items: %s", top_k, exc)
        return items[:top_k]


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
    """Build a Hansard deep link for debates and contributions.

    Written statements/answers use the day-level Hansard pages. We do not have a
    verified stable item-level anchor pattern from the API response alone, so for
    those types we link to the relevant day page rather than a guessed item URL.
    """
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
    date = raw.get("SittingDate", "")[:10]
    house = raw.get("House", "")
    text = raw.get("ContributionText", "")[:300]
    full_text = raw.get("ContributionTextFull", "")
    ext_id = raw.get("DebateSectionExtId", "")
    contrib_id = raw.get("ContributionExtId", "")
    url = (
        _hansard_url(
            house,
            date,
            ext_id,
            source_type,
            slug_text=section,
            contribution_id=contrib_id,
        )
        or fallback_url
    )

    item_id = f"{source_type[:6]}-{contrib_id or f'{date}-{member[:20]}'}"
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
        "date": date,
        "content": text,
        "rerank_text": full_text or text,
        "source_type": source_type,
        "url": url,
    }


def _fetch_hansard(
    data: Dict[str, Any],
    query: str,
    seen_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Parse a Hansard API response into a flat list of items.

    Parses Debates, Contributions, WrittenStatements, and WrittenAnswers.
    Deduplicates via seen_ids (shared across broadening retries).
    """
    if seen_ids is None:
        seen_ids = set()

    fallback_url = (
        f"https://hansard.parliament.uk/search?searchTerm={quote_plus(query)}"
    )
    items: List[Dict[str, Any]] = []

    # Debates
    for d in data.get("Debates", []):
        title = d.get("Title", "Untitled debate")
        house = d.get("House", "")
        date = d.get("SittingDate", "")[:10]
        section = d.get("DebateSection", "")
        ext_id = d.get("DebateSectionExtId", "")
        url = _hansard_url(house, date, ext_id, slug_text=title) or fallback_url

        item_id = f"debate-{ext_id or date}-{title[:30]}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        items.append(
            {
                "id": item_id,
                "title": f"{title} — {house} {section} debate",
                "date": date,
                "content": f"Parliamentary debate titled '{title}' in {house} ({section}) on {date}.",
                "rerank_text": f"{title} {section} {house} debate",
                "source_type": "debate",
                "url": url,
            }
        )

    # Contributions, WrittenStatements, WrittenAnswers — same shape
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


async def search_parliament(
    query: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    start_index: int = 1,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Search UK Parliament Hansard records with auto-broadening and reranking.

    Returns (formatted_text, structured_items). Never raises.
    """
    _this = sys.modules[__name__]
    original_query = query
    effective_query = query
    seen_ids: set = set()
    effective_date_from = date_from or _this._default_parliament_date_from()

    params: Dict[str, Any] = {"take": HANSARD_MAX_RESULTS}
    if effective_date_from:
        params["startDate"] = effective_date_from
    if date_to:
        params["endDate"] = date_to

    try:
        async with httpx.AsyncClient(timeout=HANSARD_TIMEOUT) as client:
            # Try original query
            params["searchTerm"] = query
            response = await client.get(HANSARD_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()

            items = _this._fetch_hansard(data, query, seen_ids)

            # Mark original-query hits as pinned
            for item in items:
                item["pinned"] = True

            # Always broaden and merge — let reranking pick the best
            for variant in _simplify_query(original_query):
                params["searchTerm"] = variant
                response = await client.get(HANSARD_SEARCH_URL, params=params)
                response.raise_for_status()
                data = response.json()

                new_items = _this._fetch_hansard(data, variant, seen_ids)
                items.extend(new_items)
                if new_items and effective_query == original_query:
                    effective_query = variant

    except Exception as exc:
        logger.warning("Parliament search failed for query %r: %s", query, exc)
        return f"Parliament search failed: {exc}", []

    if not items:
        return "No parliamentary results found for this topic.", []

    # Rerank by semantic similarity to the original query
    items = await _this._rerank_items(original_query, items, top_k=HANSARD_MAX_RESULTS)

    # Format like RAG: --- DOCUMENT N: title ---
    parts = []
    for i, item in enumerate(items, start_index):
        part = f"\n--- DOCUMENT {i}: {item['title']} ---\n"
        part += f"Source: UK Parliament Hansard ({item['source_type']})\n"
        part += f"Date: {item['date']}\n"
        part += f"\n[CONTENT]: {item['content']}\n"
        parts.append(part)

    fallback_url = (
        f"https://hansard.parliament.uk/search?searchTerm={quote_plus(effective_query)}"
    )
    text = "\n".join(parts) + f"\nFull Hansard search: {fallback_url}"
    return text, items
