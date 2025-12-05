"""
Setup Argilla dataset for evidence categorization labeling (Argilla v2 API).

This script:
1. Connects to Argilla instance
2. Creates a dataset with evidence category labels
3. Loads documents for manual annotation
"""

import pandas as pd
from pathlib import Path
import logging
import argilla as rg
from prompts import EVIDENCE_CATEGORIES_DEFINITION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Evidence categories (in hierarchical order)
EVIDENCE_CATEGORIES = [
    "Systematic Review and Meta-Analysis",
    "RCTs and Quasi-Experimental Studies",
    "Observational Research Studies",
    "Modelling & Simulation",
    "Policy Syntheses & Guidance Documents",
    "Qualitative & Contextual Evidence",
    "Expert Opinion and Commentary",
    "Other (Non-evidence documents)",
]

DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]


def create_and_load_dataset(
    csv_path: str,
    dataset_name: str = "evidence-categorization",
    workspace: str = "admin",
) -> None:
    """
    Create Argilla dataset and load documents.

    Args:
        csv_path: Path to CSV file with documents
        dataset_name: Name for the Argilla dataset
        workspace: Argilla workspace name
    """

    logger.info(f"Reading documents from {csv_path}")
    df = pd.read_csv(csv_path)
    logger.info(f"Loaded {len(df)} documents")

    # Define the dataset settings with questions and fields
    settings = rg.Settings(
        guidelines=f"""# Evidence Categorization Task

You will classify research and policy documents into one of 8 evidence categories based on their methodological strength and type.

{EVIDENCE_CATEGORIES_DEFINITION}

## Instructions:

1. **Read carefully**: Review the document title and abstract
2. **Identify primary method**: What is the MAIN methodological approach?
3. **Select category**: Choose the single best-fit category
4. **Rate difficulty**: How clear-cut was this classification?
5. **Add notes**: Flag edge cases or ambiguities

## Tips:

- Focus on what the document DOES, not what it references
- A policy document citing RCTs is still a policy document
- If multiple categories apply, choose the PRIMARY contribution
- When in doubt, mark as "Hard" difficulty and add notes
""",
        fields=[
            rg.TextField(
                name="title",
                title="Document Title",
            ),
            rg.TextField(
                name="abstract",
                title="Abstract/Summary",
                use_markdown=False,
            ),
            rg.TextField(
                name="metadata",
                title="Metadata",
                use_markdown=True,
            ),
        ],
        questions=[
            rg.LabelQuestion(
                name="evidence_category",
                title="Evidence Category",
                description="Select the evidence category that best describes this document",
                labels=EVIDENCE_CATEGORIES,
                required=True,
            ),
            rg.RatingQuestion(
                name="confidence",
                title="Confidence",
                description="How confident are you in this classification?",
                values=[1, 2, 3, 4, 5],
                required=True,
            ),
            rg.LabelQuestion(
                name="difficulty",
                title="Difficulty",
                description="How difficult was this classification?",
                labels=DIFFICULTY_LEVELS,
                required=False,
            ),
            rg.TextQuestion(
                name="notes",
                title="Notes",
                description="Any notes, edge cases, or ambiguities to flag?",
                required=False,
                use_markdown=False,
            ),
        ],
    )

    # Create dataset
    logger.info(f"Creating dataset '{dataset_name}'")
    dataset = rg.Dataset(
        name=dataset_name,
        workspace=workspace,
        settings=settings,
    )

    # Create the dataset on the server
    dataset.create()
    logger.info(f"Dataset created with ID: {dataset.id}")

    # Convert DataFrame to Argilla records
    logger.info(f"Preparing {len(df)} records")
    records = []

    for idx, row in df.iterrows():
        # Format metadata
        metadata_parts = []
        if pd.notna(row.get("source")):
            metadata_parts.append(f"**Source**: {row['source']}")
        if pd.notna(row.get("document_type")):
            metadata_parts.append(f"**Type**: {row['document_type']}")
        if pd.notna(row.get("year")) and row.get("year", 0) > 0:
            metadata_parts.append(f"**Year**: {int(row['year'])}")
        if pd.notna(row.get("cited_by_count")):
            metadata_parts.append(f"**Citations**: {int(row['cited_by_count'])}")
        if pd.notna(row.get("source_country")):
            metadata_parts.append(f"**Country**: {row['source_country']}")

        metadata_text = (
            "  \n".join(metadata_parts) if metadata_parts else "No metadata available"
        )

        record = {
            "title": str(row.get("title", "No title")),
            "abstract": str(row.get("abstract_or_summary", "No abstract available")),
            "metadata": metadata_text,
        }
        records.append(record)

    # Log records to the dataset
    logger.info(f"Uploading {len(records)} records to Argilla")
    dataset.records.log(records)

    logger.info("\n" + "=" * 60)
    logger.info("✓ Argilla dataset ready!")
    logger.info(f"  Dataset: {dataset_name}")
    logger.info(f"  Workspace: {workspace}")
    logger.info(f"  Records: {len(records)}")
    logger.info("=" * 60)


def main(
    csv_path: str = "inputs/references.csv",
    dataset_name: str = "evidence-categorization",
    workspace: str = "admin",
    argilla_api_url: str = "http://localhost:6900",
    argilla_api_key: str = "argilla.apikey",
):
    """
    Main function to set up Argilla dataset and load documents.

    Args:
        csv_path: Path to CSV with documents
        dataset_name: Name for the Argilla dataset
        workspace: Argilla workspace name
        argilla_api_url: Argilla API URL
        argilla_api_key: Argilla API key
    """

    # Initialize Argilla client
    logger.info(f"Connecting to Argilla at {argilla_api_url}")
    client = rg.Argilla(
        api_url=argilla_api_url,
        api_key=argilla_api_key,
    )

    # Create and load dataset
    if not Path(csv_path).exists():
        logger.error(f"CSV file not found: {csv_path}")
        return

    try:
        # Try to delete existing dataset if it exists
        try:
            existing = client.datasets(name=dataset_name, workspace=workspace)
            if existing:
                logger.info(f"Deleting existing dataset '{dataset_name}'")
                existing.delete()
        except Exception:
            pass  # Dataset doesn't exist, that's fine

        create_and_load_dataset(csv_path, dataset_name, workspace)

        logger.info(f"\n✓ Open Argilla UI at: {argilla_api_url}")
        logger.info("  Login: admin / 12345678")
        logger.info(f"  Dataset: {dataset_name}")

    except Exception as e:
        logger.error(f"Error setting up dataset: {e}", exc_info=True)


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Setup Argilla dataset for evidence categorization"
    )
    parser.add_argument(
        "--csv", default="inputs/references.csv", help="Path to CSV file with documents"
    )
    parser.add_argument(
        "--dataset-name",
        default="evidence-categorization",
        help="Name for the Argilla dataset",
    )
    parser.add_argument("--workspace", default="admin", help="Argilla workspace name")
    parser.add_argument(
        "--api-url",
        default=os.getenv("ARGILLA_API_URL", "http://localhost:6900"),
        help="Argilla API URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ARGILLA_API_KEY", "argilla.apikey"),
        help="Argilla API key",
    )

    args = parser.parse_args()

    main(
        csv_path=args.csv,
        dataset_name=args.dataset_name,
        workspace=args.workspace,
        argilla_api_url=args.api_url,
        argilla_api_key=args.api_key,
    )
