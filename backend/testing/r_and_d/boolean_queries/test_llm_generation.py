"""Test LLM-generated boolean queries retrieval performance.

This script tests query generation using LLMs across different models, temperatures,
and prompts as specified in config.yaml. Experiments run concurrently for faster execution.

Usage (run from backend directory):
    # Count only (fast - just get total counts):
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --count-only
    
    # Full results (slow - retrieve all papers):
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py
    
    # Custom output file name:
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --output-name experiment1
"""

import asyncio
import argparse
from pathlib import Path
import logging

from testing.r_and_d.boolean_queries.query_tester import (
    BooleanQueryTester,
    generate_with_llm,
    query_openalex_minimal,
    reference_df,
)
from testing.r_and_d.boolean_queries.prompts import (
    policy_atlas_v1,
    policy_atlas_v2,
)
from testing import TESTING_DIR

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main(count_only: bool = False, output_name: str = "llm"):
    """Run LLM-generated query retrieval test.

    Args:
        count_only: If True, only retrieve counts without fetching full results (much faster)
        output_name: Name prefix for output files (e.g., 'llm' -> 'llm_counts.jsonl')
    """
    # Get all research questions from reference CSV
    research_questions = reference_df["question"].tolist()

    # Paths relative to this file
    config_path = Path(__file__).parent / "config.yaml"

    # Set up the tester with LLM generator
    tester = BooleanQueryTester(
        research_questions=research_questions,
        config_path=config_path,
        prompt_generators={
            "generate_with_llm": generate_with_llm,
        },
        query_function=query_openalex_minimal,
        system_prompts={
            "policy_atlas_v1": policy_atlas_v1,
            "policy_atlas_v2": policy_atlas_v2,
        },
    )

    # Define results file path based on mode
    if count_only:
        results_file = (
            TESTING_DIR
            / "r_and_d/boolean_queries/outputs"
            / f"{output_name}_counts.jsonl"
        )
        logger.info("Running in COUNT-ONLY mode (fast, no full results)")
    else:
        results_file = (
            TESTING_DIR
            / "r_and_d/boolean_queries/outputs"
            / f"{output_name}_results.jsonl"
        )
        logger.info("Running in FULL RESULTS mode (slow, retrieves all papers)")

    logger.info("Using CONCURRENT execution")

    # Calculate total iterations
    n_questions = len(research_questions)
    n_models = len(tester.config["models"])
    n_temps = len(tester.config["temperatures"])
    n_prompts = len(tester.config["prompts"])
    n_runs = tester.config["runs_per_query"]
    max_concurrent = tester.config["max_concurrent"]
    total_iterations = n_questions * n_models * n_temps * n_prompts * n_runs
    logger.info(f"\nTotal iterations: {total_iterations}")
    logger.info(
        f"  = {n_questions} questions × {n_models} models × {n_temps} temperatures × {n_runs} runs"
    )
    logger.info(f"\nModels: {tester.config['models']}")
    logger.info(f"Temperatures: {tester.config['temperatures']}")
    logger.info(f"Runs per query: {n_runs}")
    logger.info(f"Max concurrent: {max_concurrent}")

    # Run the test (results will be saved incrementally to JSONL file)
    logger.info("\nStarting LLM query generation test...")
    logger.info("=" * 80)
    results_records = await tester.run(
        results_file=results_file,
        count_only=count_only,
    )

    logger.info("=" * 80)
    logger.info("\n✓ Completed!")
    logger.info(f"  New results processed: {len(results_records)}")
    logger.info(f"  Results saved to: {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test LLM-generated boolean queries retrieval performance"
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Only retrieve counts without fetching full results (much faster)",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="llm",
        help="Name prefix for output files (default: 'llm' produces 'llm_counts.jsonl' or 'llm_results.jsonl')",
    )
    args = parser.parse_args()

    asyncio.run(main(count_only=args.count_only, output_name=args.output_name))
