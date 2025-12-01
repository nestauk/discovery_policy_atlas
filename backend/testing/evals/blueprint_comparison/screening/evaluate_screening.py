#!/usr/bin/env python3
"""
Screening evaluation for Policy Atlas blueprint comparison.

Workflow:
1. Load evaluation topics and standardized bibliographies
2. For each bibliography entry, fetch canonical metadata from OpenAlex
3. Run the Policy Atlas relevance screening module using the topic question
4. Compare screening decisions against manual title/abstract and full-text labels
5. Emit per-topic predictions, metrics, coverage stats, and diagnostic plots
"""

import asyncio
import csv
import importlib
import json
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

try:
    plt = importlib.import_module("matplotlib.pyplot")
except ModuleNotFoundError:  # pragma: no cover
    plt = None
try:
    tqdm = importlib.import_module("tqdm").tqdm
except ModuleNotFoundError:
    tqdm = None
import pandas as pd
from difflib import SequenceMatcher

from app.services.openalex import OpenAlexService
from app.services.analysis.relevance import RelevanceService


# Load backend/.env so LLM credentials are available when running CLI scripts
def load_backend_env():
    backend_dir = Path(__file__).resolve().parents[5]
    env_path = backend_dir / ".env"
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
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


SCREENING_DIR = Path(__file__).resolve().parent
BLUEPRINT_DIR = SCREENING_DIR.parent
RESULTS_DIR = SCREENING_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

EVAL_QUERIES_CSV = BLUEPRINT_DIR / "eval_queries.csv"
BIBLIO_STD_DIR = BLUEPRINT_DIR / "bibliographies_standardized"

TITLE_MATCH_WEIGHT = 0.8
AUTHOR_MATCH_WEIGHT = 0.2
MATCH_THRESHOLD = 75.0
OPENALEX_MATCH_TIMEOUT = float(os.getenv("OPENALEX_MATCH_TIMEOUT", "20"))
SCREENING_RUNS = int(os.getenv("SCREENING_RUNS", "5"))


# ------------------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------------------


@dataclass
class TopicConfig:
    topic: str
    question: str
    boolean_query: str
    baseline_file: Path


@dataclass
class BaselineEntry:
    index: int
    title: str
    authors_raw: str
    title_positive: bool
    full_text_positive: bool
    norm_title: str
    author_tokens: set


@dataclass
class OpenAlexMatch:
    baseline_index: int
    found: bool
    doc_id: str
    title: str
    abstract: str
    authors: List[str]
    score: float


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
    cleaned = value.replace(";", ",").replace("|", ",")
    return {normalize_text(part) for part in cleaned.split(",") if normalize_text(part)}


def jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def combined_similarity(
    title_a: str, title_b: str, authors_a: set, authors_b: set
) -> float:
    title_score = SequenceMatcher(None, title_a, title_b).ratio()
    author_score = jaccard_similarity(authors_a, authors_b)
    return (TITLE_MATCH_WEIGHT * title_score + AUTHOR_MATCH_WEIGHT * author_score) * 100


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------
# Load evaluation metadata
# ------------------------------------------------------------------------------


def load_topics(index: Optional[int] = None) -> List[TopicConfig]:
    if not EVAL_QUERIES_CSV.exists():
        raise FileNotFoundError(f"eval_queries.csv not found at {EVAL_QUERIES_CSV}")

    topics: List[TopicConfig] = []
    with EVAL_QUERIES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            topic_name = row.get("Topic", "").strip()
            question = row.get("Research Question", "").strip()
            boolean_query = row.get("Policy Atlas Custom Boolean", "").strip()
            if not (topic_name and question):
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
        raise RuntimeError("No topics available for screening evaluation.")

    if index is not None:
        if index < 0 or index >= len(topics):
            raise IndexError(f"Topic index {index} out of range (0-{len(topics)-1})")
        return [topics[index]]

    return topics


def map_bibliography_file(topic_name: str) -> Path:
    exact = BIBLIO_STD_DIR / f"{topic_name}.csv"
    if exact.exists():
        return exact
    normalized = normalize_text(topic_name).replace(" ", "")
    for csv_file in BIBLIO_STD_DIR.glob("*.csv"):
        if normalize_text(csv_file.stem).replace(" ", "") == normalized:
            return csv_file
    raise FileNotFoundError(f"Standardized bibliography for '{topic_name}' not found.")


def load_bibliography(path: Path) -> List[BaselineEntry]:
    entries: List[BaselineEntry] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            title = (row.get("title") or "").strip()
            authors_raw = (row.get("authors") or "").strip()
            ta_positive = str(row.get("title_abstract_screen", "0")).strip() == "1"
            ft_positive = str(row.get("full_text_screen", "0")).strip() == "1"
            entries.append(
                BaselineEntry(
                    index=idx,
                    title=title,
                    authors_raw=authors_raw,
                    title_positive=ta_positive,
                    full_text_positive=ft_positive,
                    norm_title=normalize_text(title),
                    author_tokens=normalize_author_tokens(authors_raw),
                )
            )
    return entries


# ------------------------------------------------------------------------------
# OpenAlex lookup
# ------------------------------------------------------------------------------


def clean_title_for_lookup(title: str) -> str:
    title = title.strip()
    # Remove trailing descriptors like ": a systematic review..."
    lower = title.lower()
    for marker in [": a systematic review", ": systematic review", ": meta-analysis"]:
        idx = lower.find(marker)
        if idx != -1:
            title = title[:idx]
            break
    # Strip punctuation
    return "".join(ch for ch in title if ch.isalnum() or ch.isspace()).strip()


async def fetch_openalex_matches(
    entries: List[BaselineEntry], per_entry_limit: int = 5
) -> List[OpenAlexMatch]:
    service = OpenAlexService()
    matches: List[OpenAlexMatch] = []

    iterator = tqdm(entries, desc="  Matching titles") if tqdm else entries

    for entry in iterator:
        cleaned_title = clean_title_for_lookup(entry.title)
        if not cleaned_title:
            matches.append(
                OpenAlexMatch(
                    baseline_index=entry.index,
                    found=False,
                    doc_id=f"baseline_{entry.index}",
                    title="",
                    abstract="",
                    authors=[],
                    score=0.0,
                )
            )
            continue
        try:
            df = await asyncio.wait_for(
                service.search(query=cleaned_title, max_results=per_entry_limit),
                timeout=OPENALEX_MATCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            print(
                f"\n    [timeout] OpenAlex lookup timed out for '{entry.title[:80]}...'"
            )
            matches.append(
                OpenAlexMatch(
                    baseline_index=entry.index,
                    found=False,
                    doc_id=f"baseline_{entry.index}",
                    title="",
                    abstract="",
                    authors=[],
                    score=0.0,
                )
            )
            continue
        except Exception:
            matches.append(
                OpenAlexMatch(
                    baseline_index=entry.index,
                    found=False,
                    doc_id=f"baseline_{entry.index}",
                    title="",
                    abstract="",
                    authors=[],
                    score=0.0,
                )
            )
            continue

        best_match = select_best_openalex_match(entry, df)
        if best_match:
            matches.append(best_match)
        else:
            matches.append(
                OpenAlexMatch(
                    baseline_index=entry.index,
                    found=False,
                    doc_id=f"baseline_{entry.index}",
                    title="",
                    abstract="",
                    authors=[],
                    score=0.0,
                )
            )
    return matches


def select_best_openalex_match(
    entry: BaselineEntry, df: pd.DataFrame
) -> Optional[OpenAlexMatch]:
    best = None
    best_score = 0.0
    if df.empty:
        return None

    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        authors = row.get("authors")
        if isinstance(authors, list):
            author_tokens = {normalize_text(a) for a in authors if normalize_text(a)}
        else:
            author_tokens = set()
            authors = []

        score = combined_similarity(
            entry.norm_title, normalize_text(title), entry.author_tokens, author_tokens
        )
        if score > best_score:
            best_score = score
            best = OpenAlexMatch(
                baseline_index=entry.index,
                found=True,
                doc_id=row.get("id", f"openalex_{entry.index}"),
                title=title,
                abstract=str(row.get("abstract", "")).strip(),
                authors=authors,
                score=score,
            )

    if best and best.score >= MATCH_THRESHOLD:
        return best
    return None


# ------------------------------------------------------------------------------
# Screening via RelevanceService
# ------------------------------------------------------------------------------


async def run_relevance_screening(
    question: str, csv_path: Path, export_dir: Path
) -> Path:
    service = RelevanceService(query=question, export_dir=str(export_dir))
    try:
        await service.check_relevance(str(csv_path))
        return csv_path
    except Exception as exc:
        print(f"Relevance screening failed: {exc}")
        return None


# ------------------------------------------------------------------------------
# Metrics and plotting
# ------------------------------------------------------------------------------


def bool_from_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    value = str(value).strip().lower()
    return value in ("true", "1", "yes", "y")


def compute_classification_metrics(
    gold_positives: List[bool],
    predictions: List[bool],
) -> Dict[str, float]:
    tp = tn = fp = fn = 0
    for gold, pred in zip(gold_positives, predictions):
        if gold and pred:
            tp += 1
        elif not gold and not pred:
            tn += 1
        elif not gold and pred:
            fp += 1
        elif gold and not pred:
            fn += 1

    total = tp + tn + fp + fn
    accuracy = ((tp + tn) / total * 100) if total else 0.0
    precision = (tp / (tp + fp) * 100) if (tp + fp) else 0.0
    recall = (tp / (tp + fn) * 100) if (tp + fn) else 0.0
    specificity = (tn / (tn + fp) * 100) if (tn + fp) else 0.0
    f1 = (2 * tp / (2 * tp + fp + fn) * 100) if (2 * tp + fp + fn) else 0.0

    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
    }


def plot_confusion(metrics: Dict[str, float], output_path: Path) -> None:
    if plt is None:
        print("matplotlib not available; skipping confusion plot.")
        return
    ensure_dir(output_path.parent)
    counts = [metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]]
    labels = ["TP", "FP", "FN", "TN"]

    plt.figure(figsize=(6, 4))
    plt.bar(labels, counts, color=["#4CAF50", "#F44336", "#FF9800", "#2196F3"])
    plt.title("Confusion counts")
    plt.ylabel("Count")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    for i, val in enumerate(counts):
        plt.text(i, val + 0.5, str(val), ha="center")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_confidence_histogram(
    confidences: Sequence[float],
    gold_labels: Sequence[bool],
    output_path: Path,
) -> None:
    if plt is None:
        print("matplotlib not available; skipping confidence histogram.")
        return
    ensure_dir(output_path.parent)
    positives = [c for c, g in zip(confidences, gold_labels) if g]
    negatives = [c for c, g in zip(confidences, gold_labels) if not g]

    plt.figure(figsize=(7, 4))
    plt.hist(positives, bins=20, alpha=0.6, label="Gold Positive")
    plt.hist(negatives, bins=20, alpha=0.6, label="Gold Negative")
    plt.xlabel("Relevance confidence")
    plt.ylabel("Count")
    plt.title("Confidence distribution by gold label")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def aggregate_stage_metrics(
    metric_runs: List[Dict], stage: str
) -> Optional[Dict[str, Dict[str, float]]]:
    numeric_fields = [
        "tp",
        "tn",
        "fp",
        "fn",
        "accuracy",
        "precision",
        "recall",
        "specificity",
        "f1",
    ]
    values: Dict[str, List[float]] = {field: [] for field in numeric_fields}

    for metrics in metric_runs:
        stage_metrics = metrics.get(stage)
        if not stage_metrics:
            continue
        for field in numeric_fields:
            value = stage_metrics.get(field)
            if value is not None:
                values[field].append(float(value))

    if not any(values[field] for field in numeric_fields):
        return None

    summary = {"mean": {}, "variance": {}}
    for field, series in values.items():
        if series:
            summary["mean"][field] = statistics.mean(series)
            summary["variance"][field] = (
                statistics.pvariance(series) if len(series) > 1 else 0.0
            )

    return summary


def summarise_metric_runs(
    metric_runs: List[Optional[Dict]],
    total_entries: int,
    runs_requested: int,
) -> Dict[str, Optional[Dict]]:
    successful = [m for m in metric_runs if m]
    coverage_found = [
        m["coverage"]["found"]
        for m in successful
        if m.get("coverage") and m["coverage"].get("found") is not None
    ]
    coverage_summary = {
        "total": total_entries,
        "found_mean": statistics.mean(coverage_found) if coverage_found else 0.0,
        "found_variance": (
            statistics.pvariance(coverage_found) if len(coverage_found) > 1 else 0.0
        ),
    }

    return {
        "runs_requested": runs_requested,
        "runs_completed": len(successful),
        "coverage": coverage_summary,
        "title_abstract": aggregate_stage_metrics(successful, "title_abstract"),
        "full_text": aggregate_stage_metrics(successful, "full_text"),
    }


# ------------------------------------------------------------------------------
# Main evaluation loop
# ------------------------------------------------------------------------------


def evaluate_topic(topic: TopicConfig) -> None:
    print(f"\n{'=' * 80}")
    print(f"Screening evaluation: {topic.topic}")
    print(f"{'=' * 80}")

    topic_dir = RESULTS_DIR / topic.topic.replace(" ", "_")
    ensure_dir(topic_dir)

    baseline_entries = load_bibliography(topic.baseline_file)
    print(
        f"Found {len(baseline_entries)} bibliography entries. Matching via OpenAlex..."
    )
    matches = run_async(fetch_openalex_matches(baseline_entries))
    matched_count = sum(1 for m in matches if m.found)
    print(f"Matched {matched_count}/{len(matches)} entries.")

    lookup_path = topic_dir / "openalex_lookup.csv"
    save_openalex_lookup(matches, baseline_entries, lookup_path)

    if not any(m.found for m in matches):
        print("No entries matched to OpenAlex; skipping screening.")
        return

    run_reports: List[Dict] = []
    metrics_per_run: List[Optional[Dict]] = []

    for run_idx in range(SCREENING_RUNS):
        run_number = run_idx + 1
        run_dir = topic_dir / f"run_{run_number}"
        run_input_path = topic_dir / f"screening_input_run_{run_number}.csv"
        prepare_screening_input(matches, run_input_path)

        print(f"  ↪ Running relevance screening (run {run_number}/{SCREENING_RUNS})...")
        predictions_path = run_async(
            run_relevance_screening(topic.question, run_input_path, run_dir)
        )

        if not predictions_path:
            run_reports.append(
                {
                    "run": run_number,
                    "status": "failed",
                    "reason": "screening produced no output",
                }
            )
            metrics_per_run.append(None)
            continue

        metrics = evaluate_predictions(
            predictions_path, matches, baseline_entries, run_dir
        )
        metrics_per_run.append(metrics)
        run_reports.append({"run": run_number, "status": "success", "metrics": metrics})

    aggregate = summarise_metric_runs(
        metrics_per_run, len(baseline_entries), SCREENING_RUNS
    )

    summary_payload = {
        "runs": run_reports,
        "aggregate": aggregate,
    }

    summary_path = topic_dir / "screening_metrics.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    coverage_mean = aggregate["coverage"]["found_mean"]
    coverage_total = aggregate["coverage"]["total"]
    coverage_var = aggregate["coverage"]["found_variance"]
    print(
        f"Coverage (mean across runs): {coverage_mean:.1f}/{coverage_total} "
        f"(variance {coverage_var:.2f})"
    )

    if aggregate["title_abstract"]:
        ta_mean = aggregate["title_abstract"]["mean"]["accuracy"]
        ta_var = aggregate["title_abstract"]["variance"]["accuracy"]
        print(f"Title/Abstract accuracy: {ta_mean:.1f}% (variance {ta_var:.2f})")
    else:
        print("Title/Abstract metrics unavailable.")

    if aggregate["full_text"]:
        ft_mean = aggregate["full_text"]["mean"]["accuracy"]
        ft_var = aggregate["full_text"]["variance"]["accuracy"]
        print(f"Full Text accuracy: {ft_mean:.1f}% (variance {ft_var:.2f})")
    else:
        print("Full Text metrics unavailable.")


def save_openalex_lookup(
    matches: List[OpenAlexMatch],
    baseline_entries: List[BaselineEntry],
    output_path: Path,
) -> None:
    ensure_dir(output_path.parent)
    rows = []
    for match in matches:
        entry = baseline_entries[match.baseline_index]
        rows.append(
            {
                "baseline_index": entry.index,
                "baseline_title": entry.title,
                "baseline_authors": entry.authors_raw,
                "title_abstract_screen": int(entry.title_positive),
                "full_text_screen": int(entry.full_text_positive),
                "found": int(match.found),
                "doc_id": match.doc_id,
                "matched_title": match.title,
                "matched_authors": "; ".join(match.authors),
                "matched_abstract": match.abstract,
                "match_score": match.score,
            }
        )

    pd.DataFrame(rows).to_csv(output_path, index=False)


def prepare_screening_input(
    matches: List[OpenAlexMatch],
    output_path: Path,
) -> List[OpenAlexMatch]:
    screened = [m for m in matches if m.found]
    if not screened:
        return []

    rows = []
    for match in screened:
        abstract = match.abstract or "Abstract not available"
        rows.append(
            {
                "doc_id": match.doc_id,
                "title": match.title,
                "abstract_or_summary": abstract,
            }
        )

    ensure_dir(output_path.parent)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return screened


def evaluate_predictions(
    predictions_path: Path,
    matches: List[OpenAlexMatch],
    baseline_entries: List[BaselineEntry],
    topic_dir: Path,
) -> Dict[str, Dict]:
    df = pd.read_csv(predictions_path)
    if "is_relevant" not in df.columns:
        print(
            "Warning: screening output missing 'is_relevant' column; skipping metrics."
        )
        return {
            "coverage": {
                "total": len(baseline_entries),
                "found": sum(1 for match in matches if match.found),
            },
            "title_abstract": None,
            "full_text": None,
        }
    df["is_relevant"] = df["is_relevant"].apply(bool_from_value)

    # Map doc_id -> prediction
    prediction_map = {row["doc_id"]: row for _, row in df.iterrows()}

    title_gold = []
    full_gold = []
    preds = []
    confidences = []
    coverage_found = 0

    for match in matches:
        entry = baseline_entries[match.baseline_index]
        if not match.found:
            continue
        coverage_found += 1
        row = prediction_map.get(match.doc_id)
        if row is None or isinstance(row, pd.Series) and row.empty:
            continue
        preds.append(row["is_relevant"])
        confidences.append(float(row.get("relevance_confidence", 0.0)))
        title_gold.append(entry.title_positive)
        full_gold.append(entry.full_text_positive)

    title_metrics = compute_classification_metrics(title_gold, preds) if preds else {}
    full_metrics = compute_classification_metrics(full_gold, preds) if preds else {}

    plots_dir = topic_dir / "plots"
    if title_metrics:
        plot_confusion(title_metrics, plots_dir / "title_confusion.png")
    if full_metrics:
        plot_confusion(full_metrics, plots_dir / "full_confusion.png")
    if confidences:
        plot_confidence_histogram(
            confidences, title_gold, plots_dir / "confidence_hist.png"
        )

    return {
        "coverage": {
            "total": len(baseline_entries),
            "found": coverage_found,
        },
        "title_abstract": title_metrics,
        "full_text": full_metrics,
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
    for topic in topics:
        evaluate_topic(topic)
    print("\nScreening evaluation complete.")


if __name__ == "__main__":
    main()
