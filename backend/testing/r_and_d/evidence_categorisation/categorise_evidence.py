"""Evidence categorization script - classifies documents into 9 evidence categories."""

import asyncio
import logging
from pathlib import Path

import pandas as pd

from app.utils.llm.batch_check import LLMProcessor
from prompts import CLASSIFICATION_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

EVIDENCE_OUTPUT_FIELDS = [
    {
        "name": "evidence_category",
        "type": "str",
        "description": (
            "One of: 'Systematic Review and Meta-Analysis', 'RCTs and Quasi-Experimental Studies', "
            "'Observational Research Studies', 'Modelling & Simulation', "
            "'Policy Syntheses & Guidance Documents', 'Qualitative & Contextual Evidence', "
            "'Expert Opinion and Commentary', 'Other (Non-evidence documents)', "
            "'Unknown / Insufficient information'"
        ),
    },
    {
        "name": "evidence_confidence",
        "type": "float",
        "description": "Confidence score between 0.0 and 1.0",
    },
    {
        "name": "category_reasoning",
        "type": "str",
        "description": "Brief explanation (1-2 sentences) for the classification",
    },
]


def _format_document(doc: dict) -> str:
    """Format document dict into prompt text."""
    return f"""Classify the following document:

**Title**: {doc.get("title", "No title")}
**Abstract/Summary**: {doc.get("abstract_or_summary", "No abstract")}
**Metadata**: Source: {doc.get("source", "Unknown")}, Type: {doc.get("document_type", "Unknown")}, Year: {doc.get("year", "Unknown")}"""


async def classify_dataframe(
    df: pd.DataFrame,
    output_path: str = "evidence_results.jsonl",
    model: str = "gpt-5.2",
    batch_size: int = 10,
    sleep_time: float = 0.5,
) -> pd.DataFrame:
    """Classify all documents in a dataframe using LLMProcessor."""
    logger.info(f"Starting classification of {len(df)} documents")

    # NOTE: LLMProcessor appends to JSONL for resume capability on large batches.
    # For R&D we delete to get fresh results. For production, remove this to enable resumability.
    output_file = Path(output_path)
    if output_file.exists():
        output_file.unlink()

    text_data = {str(i): _format_document(row.to_dict()) for i, row in df.iterrows()}

    processor = LLMProcessor(
        model_name=model,
        output_path=output_path,
        system_message=CLASSIFICATION_SYSTEM_PROMPT,
        output_fields=EVIDENCE_OUTPUT_FIELDS,
    )
    await processor.process_text_data(
        text_data, batch_size=batch_size, sleep_time=sleep_time
    )

    results = pd.read_json(output_path, lines=True)
    results["id"] = results["id"].astype(int)
    df = df.join(
        results.set_index("id")[
            ["evidence_category", "evidence_confidence", "category_reasoning"]
        ]
    )

    logger.info("Classification complete")
    return df


async def run(
    input_csv: str, output_csv: str, model: str, batch_size: int, sleep_time: float
):
    """Run evidence categorization from CSV."""
    input_path = Path(input_csv)
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Reading input CSV from: {input_path}")
    df = pd.read_csv(input_path)
    logger.info(f"Loaded {len(df)} documents")

    jsonl_path = str(output_path.with_suffix(".jsonl"))
    df_classified = await classify_dataframe(
        df,
        output_path=jsonl_path,
        model=model,
        batch_size=batch_size,
        sleep_time=sleep_time,
    )

    logger.info(f"Saving results to: {output_path}")
    df_classified.to_csv(output_path, index=False)

    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)
    print(f"\nTotal documents classified: {len(df_classified)}")
    print("\nCategory distribution:")
    print(df_classified["evidence_category"].value_counts().to_string())
    print(f"\nAverage confidence: {df_classified['evidence_confidence'].mean():.3f}")
    print(
        f"Low confidence (<0.6) count: {len(df_classified[df_classified['evidence_confidence'] < 0.6])}"
    )
    print("\n" + "=" * 60)
    logger.info("Classification complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Categorize evidence documents into 9 hierarchical categories"
    )
    parser.add_argument(
        "--input", required=True, help="Path to input references.csv file"
    )
    parser.add_argument(
        "--output", required=True, help="Path to output categorised CSV file"
    )
    parser.add_argument(
        "--model", default="gpt-5.2", help="LLM model to use (default: gpt-5.2)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for processing (default: 10)",
    )
    parser.add_argument(
        "--sleep-time",
        type=float,
        default=0.5,
        help="Sleep between batches in seconds (default: 0.5)",
    )
    args = parser.parse_args()

    asyncio.run(
        run(args.input, args.output, args.model, args.batch_size, args.sleep_time)
    )
