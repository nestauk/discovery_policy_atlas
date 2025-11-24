"""Test LLM-generated boolean queries retrieval performance.

This script tests query generation using LLMs across different models, temperatures,
and prompts as specified in a config file. Experiments run concurrently for faster execution.

Usage (run from backend directory):
    cd backend
    
    # Count only (fast - just get total counts):
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --count-only
    
    # Full results (slow - retrieve all papers):
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py
    
    # Custom output file name:
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --output-name experiment1
    
    # Use alternate config file:
    uv run python testing/r_and_d/boolean_queries/test_llm_generation.py --config config_2.yaml
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
    wang_et_al_q2_prompt,
    wang_et_al_q3_prompt,
)
from testing import TESTING_DIR

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prompt registry - maps prompt names to prompt strings
PROMPT_REGISTRY = {
    "policy_atlas_v1": policy_atlas_v1,
    "policy_atlas_v2": policy_atlas_v2,
    "wang_et_al_q2_prompt": wang_et_al_q2_prompt,
    "wang_et_al_q3_prompt": wang_et_al_q3_prompt,
}


async def main(
    count_only: bool = False,
    output_name: str = "llm",
    config_file: str = "config.yaml",
    quick: bool = False,
):
    """Run LLM-generated query retrieval test.

    Args:
        count_only: If True, only retrieve counts without fetching full results (much faster)
        output_name: Name prefix for output files (e.g., 'llm' -> 'llm_counts.jsonl')
        config_file: Name of the config file to use (e.g., 'config.yaml', 'config_2.yaml')
        quick: If True, run minimal test with 1 model, 1 temperature, 1 prompt (for quick iteration)
    """
    # Get all research questions from reference CSV
    research_questions = reference_df["question"].tolist()

    # Build config path
    config_path = Path(__file__).parent / config_file

    # Load config to get prompts
    import yaml

    config = yaml.load(open(config_path, "r"), Loader=yaml.SafeLoader)

    # Quick mode: use only first model, temperature, and prompt
    if quick:
        config["models"] = config["models"][:1]
        config["temperatures"] = config["temperatures"][:1]
        config["prompts"] = config["prompts"][:1]
        config["runs_per_query"] = 1
        logger.info("QUICK MODE: Testing with 1 model, 1 temperature, 1 prompt, 1 run")

    # Build system_prompts dict from config
    prompt_names = config.get("prompts", [])
    system_prompts = {}
    for prompt_name in prompt_names:
        if prompt_name in PROMPT_REGISTRY:
            system_prompts[prompt_name] = PROMPT_REGISTRY[prompt_name]
        else:
            logger.warning(
                f"Prompt '{prompt_name}' not found in PROMPT_REGISTRY, skipping"
            )

    if not system_prompts:
        raise ValueError(
            f"No valid prompts found in config. Available: {list(PROMPT_REGISTRY.keys())}"
        )

    logger.info(f"Using prompts: {list(system_prompts.keys())}")

    # Set up the tester with LLM generator
    tester = BooleanQueryTester(
        research_questions=research_questions,
        config_path=config_path,
        prompt_generators={
            "generate_with_llm": generate_with_llm,
        },
        query_function=query_openalex_minimal,
        system_prompts=system_prompts,
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
    try:
        results_records = await tester.run(
            results_file=results_file,
            count_only=count_only,
        )
        logger.info("=" * 80)
        logger.info("\n✓ Completed!")
        logger.info(f"  New results processed: {len(results_records)}")
        logger.info(f"  Results saved to: {results_file}")
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("⚠ Interrupted by user")
        logger.info(f"  Partial results saved to: {results_file}")
        logger.info(
            "  You can resume this experiment by running the same command again"
        )


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
        "--quick",
        action="store_true",
        help="Quick test mode: uses only 1 model, 1 temperature, 1 prompt (great for testing parameters before long runs)",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="llm",
        help="Name prefix for output files (default: 'llm' produces 'llm_counts.jsonl' or 'llm_results.jsonl')",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Config file name (e.g., 'config.yaml', 'config_2.yaml')",
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            count_only=args.count_only,
            output_name=args.output_name,
            config_file=args.config,
            quick=args.quick,
        )
    )
