"""
Export labeled data from Argilla for validation.

This script:
1. Connects to Argilla
2. Retrieves submitted/labeled records
3. Exports to CSV with ground truth labels
4. Optionally filters for specific annotators or consensus
"""

import pandas as pd
from pathlib import Path
import logging
import argilla as rg
from typing import Optional, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def export_labeled_data(
    dataset_name: str = "evidence-categorization",
    workspace: str = "admin",
    output_csv: str = "inputs/validation_set.csv",
    status_filter: Optional[List[str]] = None,
    min_responses: int = 1,
) -> pd.DataFrame:
    """
    Export labeled data from Argilla to CSV.

    Args:
        dataset_name: Name of the Argilla dataset
        workspace: Argilla workspace name
        output_csv: Path to save exported CSV
        status_filter: List of record statuses to include (e.g., ["submitted", "draft"])
                      If None, includes all with at least min_responses
        min_responses: Minimum number of responses required per record

    Returns:
        DataFrame with labeled data
    """

    logger.info(f"Fetching dataset '{dataset_name}' from workspace '{workspace}'")

    # Load dataset from Argilla
    dataset = rg.FeedbackDataset.from_argilla(
        name=dataset_name,
        workspace=workspace,
    )

    logger.info(f"Dataset loaded with {len(dataset.records)} records")

    # Extract records with responses
    labeled_records = []

    for record in dataset.records:
        # Check if record has responses
        if not record.responses or len(record.responses) < min_responses:
            continue

        # Apply status filter if specified
        if status_filter:
            valid_responses = [r for r in record.responses if r.status in status_filter]
            if not valid_responses:
                continue
            responses_to_use = valid_responses
        else:
            responses_to_use = record.responses

        # Get the most recent response (or could aggregate multiple)
        # For now, taking the first submitted response
        response = responses_to_use[0]

        # Extract response values
        evidence_category = None
        confidence = None
        difficulty = None
        notes = None

        for answer in response.values:
            if answer.question_name == "evidence_category":
                evidence_category = answer.value
            elif answer.question_name == "confidence":
                confidence = answer.value
            elif answer.question_name == "difficulty":
                difficulty = answer.value
            elif answer.question_name == "notes":
                notes = answer.value

        # Build record dict
        labeled_record = {
            "title": record.fields.get("title", ""),
            "abstract_or_summary": record.fields.get("abstract", ""),
            "source": record.metadata.get("source", ""),
            "document_type": record.metadata.get("document_type", ""),
            "year": record.metadata.get("year"),
            "ground_truth_category": evidence_category,
            "annotator_confidence": confidence,
            "difficulty": difficulty,
            "labeling_notes": notes or "",
            "num_responses": len(record.responses),
            "record_id": record.id,
        }

        labeled_records.append(labeled_record)

    # Create DataFrame
    df = pd.DataFrame(labeled_records)

    if df.empty:
        logger.warning("No labeled records found!")
        return df

    logger.info(f"\n{'='*60}")
    logger.info(f"Exported {len(df)} labeled records")
    logger.info(f"{'='*60}")

    # Print summary statistics
    logger.info("\nCategory distribution:")
    logger.info(df["ground_truth_category"].value_counts().to_string())

    if "annotator_confidence" in df.columns:
        logger.info(f"\nAverage confidence: {df['annotator_confidence'].mean():.2f}")

    if "difficulty" in df.columns:
        logger.info("\nDifficulty distribution:")
        logger.info(df["difficulty"].value_counts().to_string())

    # Check for multiple responses (inter-rater reliability potential)
    multi_response = df[df["num_responses"] > 1]
    if len(multi_response) > 0:
        logger.info(f"\n{len(multi_response)} records have multiple responses")
        logger.info("(Consider calculating inter-rater agreement)")

    # Save to CSV
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    logger.info(f"\n✓ Saved validation set to: {output_path}")

    return df


def calculate_agreement(
    dataset_name: str = "evidence-categorization",
    workspace: str = "admin",
) -> pd.DataFrame:
    """
    Calculate inter-annotator agreement for records with multiple responses.

    Args:
        dataset_name: Name of the Argilla dataset
        workspace: Argilla workspace name

    Returns:
        DataFrame with agreement statistics
    """

    logger.info("Calculating inter-annotator agreement...")

    dataset = rg.FeedbackDataset.from_argilla(
        name=dataset_name,
        workspace=workspace,
    )

    multi_annotated = []

    for record in dataset.records:
        if len(record.responses) < 2:
            continue

        # Extract all category annotations
        categories = []
        for response in record.responses:
            for answer in response.values:
                if answer.question_name == "evidence_category":
                    categories.append(answer.value)

        # Calculate agreement
        if len(categories) >= 2:
            # Simple agreement: all annotators agree
            all_agree = len(set(categories)) == 1
            agreement_rate = categories.count(categories[0]) / len(categories)

            multi_annotated.append(
                {
                    "record_id": record.id,
                    "title": record.fields.get("title", "")[:60] + "...",
                    "num_annotators": len(categories),
                    "categories": categories,
                    "all_agree": all_agree,
                    "agreement_rate": agreement_rate,
                }
            )

    df_agreement = pd.DataFrame(multi_annotated)

    if not df_agreement.empty:
        logger.info(f"\nAnalyzed {len(df_agreement)} records with multiple annotations")
        logger.info(
            f"Perfect agreement: {df_agreement['all_agree'].sum()} / {len(df_agreement)}"
        )
        logger.info(
            f"Average agreement rate: {df_agreement['agreement_rate'].mean():.2%}"
        )
    else:
        logger.info("No records with multiple annotations found")

    return df_agreement


def main(
    dataset_name: str = "evidence-categorization",
    workspace: str = "admin",
    output_csv: str = "inputs/validation_set.csv",
    argilla_api_url: str = "http://localhost:6900",
    argilla_api_key: str = "argilla.apikey",
    status_filter: Optional[List[str]] = None,
    check_agreement: bool = False,
):
    """
    Main function to export labeled data from Argilla.

    Args:
        dataset_name: Name of the Argilla dataset
        workspace: Argilla workspace name
        output_csv: Path to save exported CSV
        argilla_api_url: Argilla API URL
        argilla_api_key: Argilla API key
        status_filter: List of statuses to include (e.g., ["submitted"])
        check_agreement: If True, calculate inter-annotator agreement
    """

    # Initialize Argilla client
    logger.info(f"Connecting to Argilla at {argilla_api_url}")
    rg.init(api_url=argilla_api_url, api_key=argilla_api_key)

    # Export labeled data
    df = export_labeled_data(
        dataset_name=dataset_name,
        workspace=workspace,
        output_csv=output_csv,
        status_filter=status_filter,
    )

    # Calculate agreement if requested
    if check_agreement and not df.empty:
        agreement_df = calculate_agreement(dataset_name, workspace)
        if not agreement_df.empty:
            agreement_csv = output_csv.replace(".csv", "_agreement.csv")
            agreement_df.to_csv(agreement_csv, index=False)
            logger.info(f"✓ Saved agreement analysis to: {agreement_csv}")


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Export labeled data from Argilla")
    parser.add_argument(
        "--dataset-name",
        default="evidence-categorization",
        help="Name of the Argilla dataset",
    )
    parser.add_argument("--workspace", default="admin", help="Argilla workspace name")
    parser.add_argument(
        "--output",
        default="inputs/validation_set.csv",
        help="Path to save exported CSV",
    )
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
    parser.add_argument(
        "--status",
        nargs="+",
        default=None,
        help="Filter by status (e.g., submitted draft)",
    )
    parser.add_argument(
        "--check-agreement",
        action="store_true",
        help="Calculate inter-annotator agreement",
    )

    args = parser.parse_args()

    main(
        dataset_name=args.dataset_name,
        workspace=args.workspace,
        output_csv=args.output,
        argilla_api_url=args.api_url,
        argilla_api_key=args.api_key,
        status_filter=args.status,
        check_agreement=args.check_agreement,
    )
