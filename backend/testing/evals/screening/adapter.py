import pandas as pd
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def load_and_adapt_dataset(target_config: Dict) -> pd.DataFrame:
    """
    Load and adapt dataset based on configuration.
    """
    source = target_config["dataset_source"]

    if source == "CSMeD":
        df = load_csmed(target_config["id"])
    elif source == "SYNERGY":
        df = load_synergy(target_config["id"])
    elif source == "3ie":
        df = load_three_ie(target_config["id"])
    else:
        raise ValueError(f"Unknown source: {source}")

    # Common Cleaning
    # Fill missing abstracts
    if "abstract_or_summary" not in df.columns:
        df["abstract_or_summary"] = "No abstract available"
    df["abstract_or_summary"] = df["abstract_or_summary"].fillna(
        "No abstract available"
    )

    # Ensure titles are strings
    df["title"] = df["title"].fillna("No title")

    if source == "3ie":
        return df

    return sample_data(df)


def load_csmed(review_id: str) -> pd.DataFrame:
    datasets_dir = Path(__file__).parent / "datasets"
    path = datasets_dir / "CESmed" / "CSMeD-FT-dev.csv"
    if not path.exists():
        raise FileNotFoundError(f"CSMeD dataset not found at {path}")

    # Read CSV (CSMeD can be large, but assuming it fits in memory for this script)
    df = pd.read_csv(path)

    # Filter by review_id
    df = df[df["review_id"] == review_id].copy()

    if df.empty:
        logger.warning(f"No documents found for CSMeD review_id: {review_id}")
        return pd.DataFrame(
            columns=["doc_id", "title", "abstract_or_summary", "ground_truth_relevant"]
        )

    # Map columns
    # decision: 'included' -> 1, else 0
    df["ground_truth_relevant"] = df["decision"].apply(
        lambda x: 1 if str(x).strip().lower() == "included" else 0
    )

    df = df.rename(
        columns={
            "title": "title",
            "abstract": "abstract_or_summary",
        }
    )

    # Create unique doc_id: CSMeD_{document_id}
    # document_id seems unique within the file/review
    df["doc_id"] = "CSMeD_" + df["document_id"].astype(str)

    return df[["doc_id", "title", "abstract_or_summary", "ground_truth_relevant"]]


def load_synergy(dataset_id: str) -> pd.DataFrame:
    # Find the CSV file. dataset_id is like "Hall_2012"
    datasets_dir = Path(__file__).parent / "datasets"
    path = datasets_dir / "SYNERGY" / f"{dataset_id}.csv"

    if not path.exists():
        raise FileNotFoundError(f"Could not find SYNERGY dataset: {path}")

    df = pd.read_csv(path)

    # Map columns
    # label_included -> ground_truth_relevant
    if "label_included" in df.columns:
        df["ground_truth_relevant"] = df["label_included"].astype(int)
    else:
        raise ValueError(f"Column 'label_included' not found in {dataset_id}.csv")

    df = df.rename(columns={"title": "title", "abstract": "abstract_or_summary"})

    # Create unique doc_id
    # Use row index as ID since SYNERGY files don't always have a unique ID column like 'document_id'
    # Some have 'doi', but might be missing or duplicate.
    df["doc_id"] = f"SYNERGY_{dataset_id}_" + df.index.astype(str)

    return df[["doc_id", "title", "abstract_or_summary", "ground_truth_relevant"]]


def load_three_ie(dataset_id: str) -> pd.DataFrame:
    """
    Load a 3ie evidence gap map CSV and construct positives (label=1)
    plus a pool of negatives sampled from other 3ie CSV files (label=0).
    """
    three_ie_dir = Path(__file__).parent / "datasets" / "Three_IE"
    if not three_ie_dir.exists():
        raise FileNotFoundError(f"3ie directory not found at {three_ie_dir}")

    pos_path = three_ie_dir / f"{dataset_id}.csv"
    if not pos_path.exists():
        raise FileNotFoundError(f"3ie dataset not found at {pos_path}")

    pos_df_raw = pd.read_csv(pos_path)
    positives = _standardize_three_ie_frame(pos_df_raw, dataset_id, label_value=1)

    negative_frames = []
    for csv_file in three_ie_dir.glob("*.csv"):
        if csv_file.name == pos_path.name:
            continue
        try:
            df_raw = pd.read_csv(csv_file)
            df_std = _standardize_three_ie_frame(df_raw, csv_file.stem, label_value=0)
            negative_frames.append(df_std)
        except Exception as exc:
            logger.warning(f"Failed to load 3ie negative sample from {csv_file}: {exc}")

    if not negative_frames:
        raise ValueError("No negative pools available for 3ie sampling.")

    negatives = pd.concat(negative_frames, ignore_index=True)
    if len(negatives) > 200:
        negatives = negatives.sample(n=200, random_state=42)

    combined = pd.concat([positives, negatives], ignore_index=True)
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)
    return combined


def _standardize_three_ie_frame(
    df: pd.DataFrame, dataset_label: str, label_value: int
) -> pd.DataFrame:
    """
    Map title/abstract columns and add doc_id + labels for 3ie datasets.
    """
    title_col = _match_column(df, ["title"])
    abstract_col = _match_column(df, ["abstract", "abstract_text", "summary"])

    if title_col is None:
        raise ValueError(
            f"Could not find a title column in 3ie dataset {dataset_label}"
        )
    if abstract_col is None:
        logger.warning(
            f"No abstract column detected for {dataset_label}; defaulting to empty strings."
        )
        df[abstract_col := title_col] = df[title_col]

    standardized = pd.DataFrame(
        {
            "doc_id": df.index.map(lambda idx: f"3IE_{dataset_label}_{idx}"),
            "title": df[title_col],
            "abstract_or_summary": df[abstract_col],
            "ground_truth_relevant": int(label_value),
        }
    )
    return standardized


def _match_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """
    Return the first column name whose lower-case form matches any candidate token.
    """
    lower_map = {col.strip().lower(): col for col in df.columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    return None


def sample_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sample data: All Positives + Sampled Negatives (1:3 ratio or max 200 negatives).
    """
    if df.empty:
        return df

    positives = df[df["ground_truth_relevant"] == 1]
    negatives = df[df["ground_truth_relevant"] == 0]

    n_pos = len(positives)

    # Sampling Logic
    # Sample Negatives: Select random sample to achieve a 1:3 ratio, or max 100 papers.

    if n_pos == 0:
        # If no positives, just take a small sample of negatives to test the pipeline
        n_neg = min(len(negatives), 50)
    else:
        target_neg = n_pos * 3
        n_neg = min(target_neg, 100)
        n_neg = min(
            n_neg, len(negatives)
        )  # Ensure we don't ask for more than available

    if n_neg > 0:
        sampled_negatives = negatives.sample(n=n_neg, random_state=42)
    else:
        sampled_negatives = pd.DataFrame(columns=df.columns)

    combined = pd.concat([positives, sampled_negatives])

    # Shuffle
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    logger.info(
        f"Sampled {len(positives)} positives and {len(sampled_negatives)} negatives. Total: {len(combined)}"
    )

    return combined
