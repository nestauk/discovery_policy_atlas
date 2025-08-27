#!/usr/bin/env python3
"""
Simple test script for boolean query generation - just test the function directly.
"""

import asyncio
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.analysis.references import ReferencesService


async def test_simple():
    """Simple test of the boolean query generation method."""

    # Create references service instance
    service = ReferencesService()

    # Test queries
    test_queries = [
        "carbon pricing policies effectiveness",
        "renewable energy subsidies adoption rates",
        "climate adaptation urban planning",
        "biodiversity conservation economic impact",
    ]

    print("🔍 Testing Boolean Query Generation")
    print("=" * 50)

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Test {i}] Natural query: {query}")
        try:
            boolean_query = await service.generate_boolean_query(query)
            print(f"Boolean query: {boolean_query}")
        except Exception as e:
            print(f"ERROR: {e}")

    print("\n✅ Simple test complete!")


if __name__ == "__main__":
    asyncio.run(test_simple())
