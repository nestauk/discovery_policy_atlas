#!/usr/bin/env python3
"""
Test script for debugging boolean query generation with LLM.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.core.config import settings
from app.services.analysis.prompts import BOOLEAN_QUERY_SYSTEM_PROMPT
from openai import AsyncOpenAI


# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BooleanQueryTester:
    """Test class for debugging boolean query generation."""

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY required. Set it in your .env file.")

        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def test_query_generation(
        self, natural_query: str, verbose: bool = True
    ) -> str:
        """Test boolean query generation for a single natural query."""

        if verbose:
            print(f"\n{'='*60}")
            print(f"Testing: {natural_query}")
            print(f"{'='*60}")
            print(f"Model: {settings.LLM_MODEL}")
            print("Temperature: 0.0")
            print("\nSystem prompt:")
            print(BOOLEAN_QUERY_SYSTEM_PROMPT)
            print(f"\n{'-'*40}")

        try:
            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": BOOLEAN_QUERY_SYSTEM_PROMPT},
                    {"role": "user", "content": natural_query},
                ],
                max_tokens=1000,
            )

            boolean_query = (
                response.choices[0].message.content or natural_query
            ).strip()

            if verbose:
                print("Generated boolean query:")
                print(f">>> {boolean_query}")
                print("\nToken usage:")
                print(
                    f"  Prompt tokens: {response.usage.prompt_tokens if response.usage else 'N/A'}"
                )
                print(
                    f"  Completion tokens: {response.usage.completion_tokens if response.usage else 'N/A'}"
                )
                print(
                    f"  Total tokens: {response.usage.total_tokens if response.usage else 'N/A'}"
                )

            return boolean_query

        except Exception as e:
            logger.error(f"Boolean query generation failed: {e}")
            if verbose:
                print(f"ERROR: {e}")
            return natural_query

    async def test_multiple_queries(self, queries: list[str]) -> dict[str, str]:
        """Test multiple queries and return a mapping of natural -> boolean queries."""
        results = {}

        for i, query in enumerate(queries, 1):
            print(f"\n[Test {i}/{len(queries)}]")
            boolean_query = await self.test_query_generation(query, verbose=True)
            results[query] = boolean_query

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        return results

    async def compare_queries(self, natural_query: str, num_runs: int = 3) -> list[str]:
        """Generate the same query multiple times to test consistency (should be identical with temp=0)."""
        print(f"\n{'='*60}")
        print(f"Testing consistency with {num_runs} runs (temperature=0.0)")
        print(f"Query: {natural_query}")
        print(f"{'='*60}")

        results = []
        for i in range(num_runs):
            print(f"\nRun {i+1}:")
            boolean_query = await self.test_query_generation(
                natural_query, verbose=False
            )
            results.append(boolean_query)
            print(f"  Result: {boolean_query}")

            # Small delay
            await asyncio.sleep(0.2)

        # Check consistency
        if len(set(results)) == 1:
            print(f"\n✅ All {num_runs} runs produced identical results (consistent)")
        else:
            print("\n⚠️  Results varied across runs:")
            for i, result in enumerate(results, 1):
                print(f"  Run {i}: {result}")

        return results


async def main():
    """Main test function."""
    print("🔍 Boolean Query Generation Debugger")
    print(f"Using model: {settings.LLM_MODEL}")
    print(f"OpenAI API Key configured: {'✅' if settings.OPENAI_API_KEY else '❌'}")

    if not settings.OPENAI_API_KEY:
        print(
            "❌ No OpenAI API key found. Please set OPENAI_API_KEY in your .env file."
        )
        return

    tester = BooleanQueryTester()

    # Test queries - mix of simple and complex policy-related queries
    test_queries = [
        "carbon pricing policies and their effectiveness",
        "renewable energy subsidies impact on adoption",
        "climate change adaptation strategies in urban areas",
        "biodiversity conservation and economic development",
        "mental health interventions for adolescents",
        "digital divide education technology access",
        "affordable housing policies effectiveness",
        "public health interventions pandemic preparedness",
    ]

    # Test 1: Single query with full details
    print("\n" + "=" * 80)
    print("TEST 1: Detailed single query test")
    print("=" * 80)
    await tester.test_query_generation(test_queries[0])

    # Test 2: Consistency check
    print("\n" + "=" * 80)
    print("TEST 2: Consistency check (temperature=0.0 should be deterministic)")
    print("=" * 80)
    await tester.compare_queries(test_queries[1], num_runs=3)

    # Test 3: Multiple queries
    print("\n" + "=" * 80)
    print("TEST 3: Multiple query generation")
    print("=" * 80)
    results = await tester.test_multiple_queries(test_queries[:4])

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY OF ALL RESULTS")
    print("=" * 80)
    for natural, boolean in results.items():
        print(f"\nNatural: {natural}")
        print(f"Boolean: {boolean}")

    print("\n✅ Boolean query generation testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
