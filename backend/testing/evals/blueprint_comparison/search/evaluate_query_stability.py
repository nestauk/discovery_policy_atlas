#!/usr/bin/env python3
"""
Assess stability of OpenAlex boolean query generation per topic.

For each topic in eval_queries.csv:
1. Run generate_boolean_query(question) multiple times
2. Compare the generated queries (token overlap + edit distance)
3. Save per-topic stats and the unique queries
"""

import asyncio
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from difflib import SequenceMatcher
from app.services.openalex import OpenAlexService

REPEATS = int(os.getenv("QUERY_STABILITY_REPEATS", "5"))

SEARCH_DIR = Path(__file__).resolve().parent
BLUEPRINT_DIR = SEARCH_DIR.parent
EVAL_QUERIES_CSV = BLUEPRINT_DIR / "eval_queries.csv"
RESULTS_DIR = SEARCH_DIR / "query_stability_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

EVAL_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(EVAL_LOOP)


def run_async(coro):
    return EVAL_LOOP.run_until_complete(coro)


@dataclass
class TopicConfig:
    topic: str
    question: str


def load_topics(index: Optional[int] = None) -> List[TopicConfig]:
    if not EVAL_QUERIES_CSV.exists():
        raise FileNotFoundError(f"Missing eval_queries.csv at {EVAL_QUERIES_CSV}")

    topics: List[TopicConfig] = []
    with EVAL_QUERIES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            topic = row.get("Topic", "").strip()
            question = row.get("Research Question", "").strip()
            if topic and question:
                topics.append(TopicConfig(topic=topic, question=question))

    if not topics:
        raise RuntimeError("No topics found in eval_queries.csv")

    if index is not None:
        if index < 0 or index >= len(topics):
            raise IndexError(f"Topic index {index} out of range (0-{len(topics)-1})")
        return [topics[index]]

    return topics


async def generate_query(question: str) -> str:
    service = OpenAlexService()
    result = await service.generate_boolean_query(question)
    return result or question


def tokenize(query: str) -> List[str]:
    # Strip parentheses/quotes and split by whitespace/AND/OR/NOT
    replace_chars = '()"'
    for ch in replace_chars:
        query = query.replace(ch, " ")
    separators = [" AND ", " OR ", " NOT ", ","]
    for sep in separators:
        query = query.replace(sep, " ")
    return [token.strip().lower() for token in query.split() if token.strip()]


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def compare_queries(queries: List[str]) -> Dict[str, float]:
    if len(queries) < 2:
        return {
            "num_unique": len(set(queries)),
            "avg_jaccard": 1.0,
            "avg_edit_ratio": 1.0,
        }

    tokens = [tokenize(q) for q in queries]
    jaccard_scores = []
    edit_scores = []

    for i in range(len(queries)):
        for j in range(i + 1, len(queries)):
            jaccard_scores.append(jaccard(tokens[i], tokens[j]))
            edit_scores.append(SequenceMatcher(None, queries[i], queries[j]).ratio())

    avg_jaccard = sum(jaccard_scores) / len(jaccard_scores)
    avg_edit = sum(edit_scores) / len(edit_scores)

    return {
        "num_unique": len(set(queries)),
        "avg_jaccard": avg_jaccard,
        "avg_edit_ratio": avg_edit,
    }


def parse_topic_index() -> Optional[int]:
    for arg in os.sys.argv[1:]:
        if arg.startswith("--topic-index="):
            value = arg.split("=", 1)[1]
            if value.isdigit():
                return int(value)
            raise ValueError(f"Invalid topic index '{value}'")
    return None


def main():
    topics = load_topics(parse_topic_index())
    rows = []

    for topic in topics:
        print(f"\nEvaluating query stability for: {topic.topic}")
        generated = []
        for i in range(REPEATS):
            result = run_async(generate_query(topic.question))
            generated.append(result.strip())
            print(f"  Run {i+1}: {result}")

        stats = compare_queries(generated)
        rows.append(
            {
                "topic": topic.topic,
                "num_runs": REPEATS,
                "num_unique": stats["num_unique"],
                "avg_jaccard": stats["avg_jaccard"],
                "avg_edit_ratio": stats["avg_edit_ratio"],
                "queries": " ||| ".join(generated),
            }
        )

    output_path = RESULTS_DIR / "query_stability.csv"
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topic",
                "num_runs",
                "num_unique",
                "avg_jaccard",
                "avg_edit_ratio",
                "queries",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved query stability results to {output_path}")


if __name__ == "__main__":
    main()
