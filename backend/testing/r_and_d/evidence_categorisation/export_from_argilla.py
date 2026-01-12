"""
Export labeled data from Argilla for validation (Argilla v2 API).

This script:
1. Connects to Argilla
2. Retrieves submitted/labeled records
3. Exports to CSV with ground truth labels
"""

import pandas as pd
from pathlib import Path
import logging
import argilla as rg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def export_labeled_data(
    client: rg.Argilla,
    dataset_name: str = "evidence-categorization",
    workspace: str = "default",
    output_csv: str = "inputs/validation_set.csv",
    min_responses: int = 1,
) -> pd.DataFrame:
    """
    Export labeled data from Argilla to CSV.

    Args:
        client: Argilla client instance
        dataset_name: Name of the Argilla dataset
        workspace: Argilla workspace name
        output_csv: Path to save exported CSV
        min_responses: Minimum number of responses required per record

    Returns:
        DataFrame with labeled data
    """

    logger.info(f"Fetching dataset '{dataset_name}' from workspace '{workspace}'")

    # Load dataset from Argilla
    dataset = client.datasets(name=dataset_name, workspace=workspace)

    if not dataset:
        logger.error(f"Dataset '{dataset_name}' not found in workspace '{workspace}'")
        return pd.DataFrame()

    logger.info("Dataset loaded")

    # Extract records with responses
    labeled_records = []
    total_records = 0

    for record in dataset.records:
        total_records += 1

        # Check if record has responses
        # In Argilla v2, record.responses is a RecordResponses object that supports dict-like access:
        # record.responses['evidence_category'] returns [{'value': 'Some Category'}]
        if not hasattr(record, "responses") or not record.responses:
            logger.debug(
                f"Record {record.id}: No responses attribute or empty responses"
            )
            continue

        logger.debug(f"Record {record.id}: Has responses: {record.responses}")

        # Use the responses object directly (it supports dict-like access)
        responses = record.responses

        # Extract response values from the dict-like structure
        # Each question has a list of responses, we take the first one [0]
        evidence_category = None
        confidence = None
        difficulty = None
        notes = None

        # Get values from the responses object
        # RecordResponses['question'] returns list of Response objects
        # Each Response object has a .value attribute (not a dict!)
        try:
            evidence_cat_list = responses["evidence_category"]
            if evidence_cat_list:
                evidence_category = evidence_cat_list[
                    0
                ].value  # Access .value attribute directly
                logger.debug(
                    f"Record {record.id}: Extracted evidence_category = {evidence_category}"
                )
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            logger.debug(f"Record {record.id}: Error extracting evidence_category: {e}")
            pass

        try:
            confidence_list = responses["confidence"]
            if confidence_list:
                confidence = confidence_list[0].value
        except (KeyError, IndexError, TypeError, AttributeError):
            pass

        try:
            difficulty_list = responses["difficulty"]
            if difficulty_list:
                difficulty = difficulty_list[0].value
        except (KeyError, IndexError, TypeError, AttributeError):
            pass

        try:
            notes_list = responses["notes"]
            if notes_list:
                notes = notes_list[0].value
        except (KeyError, IndexError, TypeError, AttributeError):
            pass

        # Skip if no evidence_category was provided (required field)
        if not evidence_category:
            continue

        # Get fields
        title = record.fields.get("title", "")
        abstract = record.fields.get("abstract", "")

        # Get metadata from fields (it was stored as a text field)
        metadata_text = record.fields.get("metadata", "")

        # Try to extract structured metadata if available, otherwise use empty strings
        source = ""
        document_type = ""
        year = None

        # Parse metadata text if it exists
        if metadata_text and metadata_text != "No metadata available":
            for line in metadata_text.split("\n"):
                if "Source:" in line:
                    source = line.split("Source:")[1].strip().replace("**", "")
                elif "Type:" in line:
                    document_type = line.split("Type:")[1].strip().replace("**", "")
                elif "Year:" in line:
                    try:
                        year = int(line.split("Year:")[1].strip().replace("**", ""))
                    except ValueError:
                        pass

        # Build record dict
        # Count num_responses - count how many questions have responses
        num_responses = 0
        for q in ["evidence_category", "confidence", "difficulty", "notes"]:
            try:
                if responses[q]:
                    num_responses += 1
            except (KeyError, TypeError):
                pass

        labeled_record = {
            "title": title,
            "abstract_or_summary": abstract,
            "source": source,
            "document_type": document_type,
            "year": year,
            "ground_truth_category": evidence_category,
            "annotator_confidence": confidence,
            "difficulty": difficulty,
            "labeling_notes": notes or "",
            "num_responses": num_responses,
            "record_id": str(record.id) if hasattr(record, "id") else "",
        }

        labeled_records.append(labeled_record)

    # Create DataFrame
    df = pd.DataFrame(labeled_records)

    if df.empty:
        logger.warning(
            f"No labeled records found! ({total_records} total records in dataset)"
        )
        logger.info("Make sure you've submitted some annotations in the Argilla UI")
        return df

    logger.info(f"\n{'='*60}")
    logger.info(f"Exported {len(df)} labeled records (out of {total_records} total)")
    logger.info(f"{'='*60}")

    # Print summary statistics
    logger.info("\nCategory distribution:")
    logger.info(df["ground_truth_category"].value_counts().to_string())

    if (
        "annotator_confidence" in df.columns
        and df["annotator_confidence"].notna().any()
    ):
        logger.info(f"\nAverage confidence: {df['annotator_confidence'].mean():.2f}")

    if "difficulty" in df.columns and df["difficulty"].notna().any():
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


def main(
    dataset_name: str = "evidence-categorization",
    workspace: str = "default",
    output_csv: str = "inputs/validation_set.csv",
    argilla_api_url: str = "http://localhost:6900",
    argilla_api_key: str = "argilla.apikey",
):
    """
    Main function to export labeled data from Argilla.

    Args:
        dataset_name: Name of the Argilla dataset
        workspace: Argilla workspace name
        output_csv: Path to save exported CSV
        argilla_api_url: Argilla API URL
        argilla_api_key: Argilla API key
    """

    # Initialize Argilla client
    logger.info(f"Connecting to Argilla at {argilla_api_url}")
    client = rg.Argilla(
        api_url=argilla_api_url,
        api_key=argilla_api_key,
    )

    # Export labeled data
    df = export_labeled_data(
        client=client,
        dataset_name=dataset_name,
        workspace=workspace,
        output_csv=output_csv,
    )

    if not df.empty:
        logger.info(f"\n✓ Successfully exported {len(df)} labeled records")
        logger.info(f"  File: {output_csv}")
        logger.info(
            "\nYou can now use this validation set to evaluate your classifier!"
        )
    else:
        logger.warning("\n⚠ No labeled data to export")
        logger.info("  Please label some documents in Argilla first")
        logger.info("  Then run this script again")


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Export labeled data from Argilla")
    parser.add_argument(
        "--dataset-name",
        default="evidence-categorization",
        help="Name of the Argilla dataset",
    )
    parser.add_argument("--workspace", default="default", help="Argilla workspace name")
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

    args = parser.parse_args()

    main(
        dataset_name=args.dataset_name,
        workspace=args.workspace,
        output_csv=args.output,
        argilla_api_url=args.api_url,
        argilla_api_key=args.api_key,
    )
