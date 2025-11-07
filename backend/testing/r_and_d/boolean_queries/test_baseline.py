"""Test baseline boolean queries retrieval performance.
 
Usage (run from backend directory):
    # Count only (fast - just get total counts):
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_baseline.py --count-only
    
    # Full results (slow - retrieve all papers):
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_baseline.py
"""

import asyncio
import argparse
from pathlib import Path
import logging

from testing.r_and_d.boolean_queries.query_tester import (
    BooleanQueryTester,
    use_baseline_query,
    query_openalex_minimal,
    reference_df,
)
from testing.r_and_d.boolean_queries.prompts import policy_atlas_v2
from testing import TESTING_DIR

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main(count_only: bool = False):
    """Run baseline query retrieval test.

    Args:
        count_only: If True, only retrieve counts without fetching full results (much faster)
    """
    # Get all research questions from reference CSV
    research_questions = reference_df["question"].tolist()

    # Paths relative to this file
    config_path = Path(__file__).parent / "config.yaml"

    # Set up the tester with only the baseline query generator
    tester = BooleanQueryTester(
        research_questions=research_questions,
        config_path=config_path,
        prompt_generators={
            "use_baseline_query": use_baseline_query,
        },
        query_function=query_openalex_minimal,
        system_prompts={
            "policy_atlas_v2": policy_atlas_v2,
        },
    )

    # Override config to avoid unnecessary iterations (baseline doesn't use model/temperature)
    tester.config["models"] = ["baseline"]  # Dummy value, not used
    tester.config["temperatures"] = [0]  # Dummy value, not used
    tester.config["runs_per_query"] = 1  # Only run once

    # Define results file path based on mode
    if count_only:
        results_file = (
            TESTING_DIR / "r_and_d/boolean_queries/outputs/baseline_counts.jsonl"
        )
        logger.info("Running in COUNT-ONLY mode (fast, no full results)")
    else:
        results_file = (
            TESTING_DIR / "r_and_d/boolean_queries/outputs/baseline_results.jsonl"
        )
        logger.info("Running in FULL RESULTS mode (slow, retrieves all papers)")

    # Run the test (results will be saved incrementally to JSONL file)
    logger.info("Running baseline query retrieval test...")
    results_records = await tester.run(
        generator_names=["use_baseline_query"],
        prompt_names=["policy_atlas_v2"],  # Not used by baseline but required
        results_file=results_file,
        count_only=count_only,
    )

    logger.info("\n✓ Completed!")
    logger.info(f"  New results processed: {len(results_records)}")
    logger.info(f"  Results saved to: {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test baseline boolean queries retrieval performance"
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Only retrieve counts without fetching full results (much faster)",
    )
    args = parser.parse_args()

    asyncio.run(main(count_only=args.count_only))
