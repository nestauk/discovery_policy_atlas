#!/usr/bin/env python3
"""
Search evaluation for Policy Atlas blueprint comparison.

Workflow:
1. Load evaluation topics from eval_queries.csv
2. For each topic, run OpenAlex search for multiple top-N values
3. Fuzzy-match retrieved papers (title + authors) against the standardized blueprint bibliography
4. Calculate recall/precision metrics for title/abstract and full-text positives
5. Emit per-topic CSV summaries, matched/unmatched tables, and recall plots
"""

import asyncio
import csv
import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    plt = importlib.import_module("matplotlib.pyplot")
except ModuleNotFoundError:  # pragma: no cover - plotting optional
    plt = None
import pandas as pd
from difflib import SequenceMatcher

from app.services.openalex import OpenAlexService


# Load backend/.env so OPENAI / LLM vars are available when running via CLI
def load_backend_env():
    backend_dir = Path(__file__).resolve().parents[5]
    env_path = backend_dir / ".env"
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_backend_env()

# Dedicated asyncio loop for this script
EVAL_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(EVAL_LOOP)


def run_async(coro):
    return EVAL_LOOP.run_until_complete(coro)


# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

TOP_N_DEFAULT = [10, 25, 50, 100, 200]
MATCH_THRESHOLD = 70.0  # combined score threshold (0-100)
TITLE_WEIGHT = 0.75
AUTHOR_WEIGHT = 0.25

SEARCH_DIR = Path(__file__).resolve().parent
BLUEPRINT_DIR = SEARCH_DIR.parent
PROJECT_ROOT = BLUEPRINT_DIR.parents[3]

EVAL_QUERIES_CSV = BLUEPRINT_DIR / "eval_queries.csv"
BIBLIO_DIR = BLUEPRINT_DIR / "bibliographies"
BIBLIO_STD_DIR = BLUEPRINT_DIR / "bibliographies_standardized"
RESULTS_DIR = SEARCH_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------------------


@dataclass
class TopicConfig:
    topic: str
    question: str
    boolean_query: str
    baseline_file: Path


@dataclass
class BibliographyEntry:
    index: int
    title: str
    authors_raw: str
    title_positive: bool
    full_text_positive: bool
    norm_title: str
    author_tokens: set


@dataclass
class RetrievedEntry:
    index: int
    title: str
    authors: List[str]
    abstract: str
    doi: str
    publication_year: Optional[int]
    norm_title: str
    author_tokens: set


# ------------------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------------------


def normalize_text(value: str) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    for ch in "',.:;!?()[]{}<>\"`|/\\+-=_*#":
        value = value.replace(ch, " ")
    return " ".join(value.split())


def normalize_author_tokens(value: str) -> set:
    if not value:
        return set()
    delimiters = [";", "|"]
    for delim in delimiters:
        value = value.replace(delim, ",")
    parts = []
    for token in value.split(","):
        token = token.strip()
        if token:
            parts.append(token)
    return {normalize_text(part) for part in parts if normalize_text(part)}


def jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def combined_similarity(b_entry: BibliographyEntry, r_entry: RetrievedEntry) -> float:
    title_score = SequenceMatcher(None, b_entry.norm_title, r_entry.norm_title).ratio()
    author_score = jaccard_similarity(b_entry.author_tokens, r_entry.author_tokens)
    combined = TITLE_WEIGHT * title_score + AUTHOR_WEIGHT * author_score
    return combined * 100


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def tokenize_query(query: str) -> List[str]:
    clean = query.replace("(", " ").replace(")", " ").replace('"', " ")
    for sep in [" AND ", " OR ", " NOT ", ","]:
        clean = clean.replace(sep, " ")
    return [token.strip().lower() for token in clean.split() if token.strip()]


def compare_queries(reference: str, candidate: str) -> Dict[str, float]:
    ref_tokens = tokenize_query(reference)
    cand_tokens = tokenize_query(candidate)

    set_ref, set_cand = set(ref_tokens), set(cand_tokens)
    if set_ref or set_cand:
        jaccard = (
            len(set_ref & set_cand) / len(set_ref | set_cand)
            if set_ref | set_cand
            else 1.0
        )
    else:
        jaccard = 1.0
    edit_ratio = SequenceMatcher(None, reference, candidate).ratio()
    return {
        "custom_query": reference,
        "generated_query": candidate,
        "query_token_overlap": jaccard,
        "query_edit_ratio": edit_ratio,
    }


# ------------------------------------------------------------------------------
# Loading functions
# ------------------------------------------------------------------------------


def load_eval_topics(index: Optional[int] = None) -> List[TopicConfig]:
    if not EVAL_QUERIES_CSV.exists():
        raise FileNotFoundError(f"eval_queries.csv not found at {EVAL_QUERIES_CSV}")

    topics: List[TopicConfig] = []
    with EVAL_QUERIES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            topic_name = row.get("Topic", "").strip()
            question = row.get("Research Question", "").strip()
            boolean_query = row.get("Policy Atlas Custom Boolean", "").strip()

            if not (topic_name and question and boolean_query):
                continue

            baseline_file = map_bibliography_file(topic_name)
            topics.append(
                TopicConfig(
                    topic=topic_name,
                    question=question,
                    boolean_query=boolean_query,
                    baseline_file=baseline_file,
                )
            )

    if not topics:
        raise RuntimeError("No topics loaded from eval_queries.csv")

    if index is not None:
        if index < 0 or index >= len(topics):
            raise IndexError(f"Topic index {index} out of range (0-{len(topics)-1})")
        return [topics[index]]

    return topics


def map_bibliography_file(topic_name: str) -> Path:
    exact = BIBLIO_STD_DIR / f"{topic_name}.csv"
    if exact.exists():
        return exact

    normalized_target = normalize_text(topic_name).replace(" ", "")
    for csv_file in BIBLIO_STD_DIR.glob("*.csv"):
        normalized_candidate = normalize_text(csv_file.stem).replace(" ", "")
        if normalized_target == normalized_candidate:
            return csv_file

    raise FileNotFoundError(
        f"Standardized bibliography for topic '{topic_name}' not found in {BIBLIO_STD_DIR}"
    )


def load_bibliography(path: Path) -> List[BibliographyEntry]:
    entries: List[BibliographyEntry] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            title = (row.get("title") or "").strip()
            authors_raw = (row.get("authors") or "").strip()
            ta_positive = str(row.get("title_abstract_screen", "0")).strip() == "1"
            ft_positive = str(row.get("full_text_screen", "0")).strip() == "1"

            entry = BibliographyEntry(
                index=idx,
                title=title,
                authors_raw=authors_raw,
                title_positive=ta_positive,
                full_text_positive=ft_positive,
                norm_title=normalize_text(title),
                author_tokens=normalize_author_tokens(authors_raw),
            )
            entries.append(entry)
    return entries


# ------------------------------------------------------------------------------
# Retrieval
# ------------------------------------------------------------------------------


async def fetch_openalex_results(query: str, max_results: int) -> pd.DataFrame:
    service = OpenAlexService()
    df = await service.search(query=query, max_results=max_results)
    return df


def run_openalex_search(query: str, max_results: int) -> pd.DataFrame:
    print(f"Running OpenAlex search (limit={max_results})...")
    return run_async(fetch_openalex_results(query, max_results))


def generate_openalex_query(question: str) -> str:
    async def _generate() -> str:
        service = OpenAlexService()
        try:
            query = await service.generate_boolean_query(question)
            return query or question
        except Exception as exc:
            print(
                f"Warning: failed to generate boolean query ({exc}). Using question text."
            )
            return question

    return run_async(_generate())


def serialize_retrieved_entries(df: pd.DataFrame) -> List[RetrievedEntry]:
    entries: List[RetrievedEntry] = []
    for idx, row in df.iterrows():
        authors = row.get("authors")
        if isinstance(authors, list):
            author_tokens = {normalize_text(a) for a in authors if normalize_text(a)}
        else:
            author_tokens = set()

        entry = RetrievedEntry(
            index=idx,
            title=str(row.get("title", "")).strip(),
            authors=authors if isinstance(authors, list) else [],
            abstract=str(row.get("abstract", "")).strip(),
            doi=str(row.get("doi", "")).strip(),
            publication_year=row.get("publication_year"),
            norm_title=normalize_text(str(row.get("title", ""))),
            author_tokens=author_tokens,
        )
        entries.append(entry)
    return entries


def save_references_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_directory(path.parent)
    df_to_write = df.copy()
    df_to_write["authors"] = df_to_write["authors"].apply(
        lambda x: "; ".join(x) if isinstance(x, list) else ""
    )
    df_to_write.to_csv(path, index=False)


# ------------------------------------------------------------------------------
# Matching logic
# ------------------------------------------------------------------------------


def match_entries(
    baseline_entries: List[BibliographyEntry],
    retrieved_entries: List[RetrievedEntry],
) -> Dict[int, Tuple[int, float]]:
    """Return mapping baseline_index -> (retrieved_index, score)."""
    matches: Dict[int, Tuple[int, float]] = {}
    used_retrieved = set()

    for b_entry in baseline_entries:
        best_idx = None
        best_score = 0.0

        for r_entry in retrieved_entries:
            if r_entry.index in used_retrieved:
                continue
            score = combined_similarity(b_entry, r_entry)
            if score > best_score:
                best_score = score
                best_idx = r_entry.index

        if best_idx is not None and best_score >= MATCH_THRESHOLD:
            matches[b_entry.index] = (best_idx, best_score)
            used_retrieved.add(best_idx)

    return matches


# ------------------------------------------------------------------------------
# Metrics & plotting
# ------------------------------------------------------------------------------


def compute_metrics(
    baseline_entries: List[BibliographyEntry],
    matches: Dict[int, Tuple[int, float]],
    retrieved_count: int,
) -> Dict[str, float]:
    total_title_pos = sum(1 for e in baseline_entries if e.title_positive)
    total_full_pos = sum(1 for e in baseline_entries if e.full_text_positive)

    title_matches = sum(
        1 for e in baseline_entries if e.title_positive and e.index in matches
    )
    full_matches = sum(
        1 for e in baseline_entries if e.full_text_positive and e.index in matches
    )

    recall_title = (
        (title_matches / total_title_pos) * 100 if total_title_pos > 0 else 0.0
    )
    recall_full = (full_matches / total_full_pos) * 100 if total_full_pos > 0 else 0.0

    precision_title = (
        (title_matches / retrieved_count) * 100 if retrieved_count > 0 else 0.0
    )
    precision_full = (
        (full_matches / retrieved_count) * 100 if retrieved_count > 0 else 0.0
    )

    return {
        "baseline_title_abstract_positives": total_title_pos,
        "baseline_full_text_positives": total_full_pos,
        "matches_to_title_abstract": title_matches,
        "matches_to_full_text": full_matches,
        "recall_title_abstract": recall_title,
        "recall_full_text": recall_full,
        "precision_title_abstract": precision_title,
        "precision_full_text": precision_full,
        "retrieved_count": retrieved_count,
    }


def plot_recall_curve(
    topic: str,
    topn_values: Sequence[int],
    recall_title: Sequence[float],
    recall_full: Sequence[float],
    output_dir: Path,
) -> None:
    if plt is None:
        print("matplotlib not available; skipping recall plots.")
        return
    ensure_directory(output_dir)
    plt.figure(figsize=(8, 5))
    plt.plot(topn_values, recall_title, marker="o", label="Title/Abstract Recall")
    plt.plot(topn_values, recall_full, marker="s", label="Full Text Recall")
    plt.xlabel("Top-N Retrieved")
    plt.ylabel("Recall (%)")
    plt.title(f"Recall vs N for {topic}")
    plt.ylim(0, 105)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "recall_curve.png")
    plt.close()

    # Precision plot
    plt.figure(figsize=(8, 5))
    plt.plot(topn_values, recall_title, marker="o", label="Title/Abstract Recall")
    plt.plot(topn_values, recall_full, marker="s", label="Full Text Recall")
    plt.xlabel("Top-N Retrieved")
    plt.ylabel("Metric (%)")
    plt.title(f"Recall metrics for {topic}")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "recall_metrics.png")
    plt.close()


# ------------------------------------------------------------------------------
# Main evaluation loop
# ------------------------------------------------------------------------------


def evaluate_topic(topic: TopicConfig, topn_values: Sequence[int]) -> None:
    print(f"\n{'=' * 80}")
    print(f"Evaluating topic: {topic.topic}")
    print(f"{'=' * 80}")

    topic_dir = RESULTS_DIR / topic.topic.replace(" ", "_")
    ensure_directory(topic_dir)

    baseline_entries = load_bibliography(topic.baseline_file)
    max_n = max(topn_values)

    # Generate OpenAlex-friendly query from research question
    openalex_query = generate_openalex_query(topic.question)
    print(f"OpenAlex query: {openalex_query}")
    query_similarity = compare_queries(topic.boolean_query, openalex_query)

    # Run OpenAlex search once per topic
    df = run_openalex_search(openalex_query, max_n)
    retrieved_entries = serialize_retrieved_entries(df)

    metrics_rows = []
    recall_title_values = []
    recall_full_values = []

    for n in topn_values:
        subset_df = df.iloc[: min(n, len(df))].copy()
        subset_entries = retrieved_entries[: min(n, len(retrieved_entries))]

        sub_dir = topic_dir / f"top_{n}"
        ensure_directory(sub_dir)
        save_references_csv(subset_df, sub_dir / "references.csv")

        matches = match_entries(baseline_entries, subset_entries)
        metrics = compute_metrics(baseline_entries, matches, len(subset_entries))

        # Save matched/unmatched details
        save_matching_tables(baseline_entries, subset_entries, matches, sub_dir)

        metrics_row = {
            "top_n": n,
            "query": openalex_query,
            **query_similarity,
            **metrics,
        }
        metrics_rows.append(metrics_row)
        recall_title_values.append(metrics["recall_title_abstract"])
        recall_full_values.append(metrics["recall_full_text"])

        print(
            f"Top {n}: Recall TA={metrics['recall_title_abstract']:.1f}%, "
            f"Recall FT={metrics['recall_full_text']:.1f}%, "
            f"Precision TA={metrics['precision_title_abstract']:.1f}%"
        )

    # Write summary CSV and plots
    summary_path = topic_dir / "search_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=metrics_rows[0].keys())
        writer.writeheader()
        writer.writerows(metrics_rows)

    plot_recall_curve(
        topic.topic,
        topn_values,
        recall_title_values,
        recall_full_values,
        topic_dir / "plots",
    )


def save_matching_tables(
    baseline_entries: List[BibliographyEntry],
    retrieved_entries: List[RetrievedEntry],
    matches: Dict[int, Tuple[int, float]],
    output_dir: Path,
) -> None:
    ensure_directory(output_dir)
    matched_rows = []
    unmatched_baseline_rows = []
    unmatched_retrieved_rows = []

    used_retrieved = set()
    for b_idx, (r_idx, score) in matches.items():
        b_entry = baseline_entries[b_idx]
        r_entry = next((e for e in retrieved_entries if e.index == r_idx), None)
        if not r_entry:
            continue
        used_retrieved.add(r_idx)
        matched_rows.append(
            {
                "baseline_index": b_entry.index,
                "retrieved_index": r_entry.index,
                "baseline_title": b_entry.title,
                "baseline_authors": b_entry.authors_raw,
                "retrieved_title": r_entry.title,
                "retrieved_authors": "; ".join(r_entry.authors),
                "score": score,
                "title_positive": int(b_entry.title_positive),
                "full_text_positive": int(b_entry.full_text_positive),
            }
        )

    for entry in baseline_entries:
        if entry.index not in matches:
            unmatched_baseline_rows.append(
                {
                    "baseline_index": entry.index,
                    "title": entry.title,
                    "authors": entry.authors_raw,
                    "title_positive": int(entry.title_positive),
                    "full_text_positive": int(entry.full_text_positive),
                }
            )

    for r_entry in retrieved_entries:
        if r_entry.index not in used_retrieved:
            unmatched_retrieved_rows.append(
                {
                    "retrieved_index": r_entry.index,
                    "title": r_entry.title,
                    "authors": "; ".join(r_entry.authors),
                    "doi": r_entry.doi,
                }
            )

    with (output_dir / "matched.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=matched_rows[0].keys()
            if matched_rows
            else [
                "baseline_index",
                "retrieved_index",
                "baseline_title",
                "baseline_authors",
                "retrieved_title",
                "retrieved_authors",
                "score",
                "title_positive",
                "full_text_positive",
            ],
        )
        writer.writeheader()
        writer.writerows(matched_rows)

    with (output_dir / "unmatched_baseline.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=unmatched_baseline_rows[0].keys()
            if unmatched_baseline_rows
            else [
                "baseline_index",
                "title",
                "authors",
                "title_positive",
                "full_text_positive",
            ],
        )
        writer.writeheader()
        writer.writerows(unmatched_baseline_rows)

    with (output_dir / "unmatched_retrieved.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=unmatched_retrieved_rows[0].keys()
            if unmatched_retrieved_rows
            else ["retrieved_index", "title", "authors", "doi"],
        )
        writer.writeheader()
        writer.writerows(unmatched_retrieved_rows)


# ------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------


def parse_topic_index() -> Optional[int]:
    for arg in os.sys.argv[1:]:
        if arg.startswith("--topic-index="):
            value = arg.split("=", 1)[1]
            if value.isdigit():
                return int(value)
            raise ValueError(f"Invalid topic index '{value}'")
    return None


def main():
    topn_values = TOP_N_DEFAULT
    topic_index = parse_topic_index()
    topics = load_eval_topics(topic_index)
    for topic in topics:
        evaluate_topic(topic, topn_values)

    print("\nSearch evaluation complete.")


if __name__ == "__main__":
    main()
