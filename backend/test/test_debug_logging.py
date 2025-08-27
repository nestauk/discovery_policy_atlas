#!/usr/bin/env python3
"""
Test script to verify debug logging is working in the references service.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.analysis.references import ReferencesService


# Set up logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to see all messages
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Also set the app logger specifically
logger = logging.getLogger("app.services.analysis.references")
logger.setLevel(logging.DEBUG)


async def test_debug_logging():
    """Test the debug logging functionality."""

    print("🔍 Testing Debug Logging in References Service")
    print("=" * 60)
    print("You should see detailed log messages below:")
    print("-" * 60)

    # Create service instance with a temp directory
    service = ReferencesService(export_dir="./temp/debug_test")

    # Test 1: Direct boolean query generation
    print("\n[TEST 1] Direct boolean query generation:")
    test_query = "carbon pricing policies effectiveness"
    try:
        boolean_query = await service.generate_boolean_query(test_query)
        print(f"Result: {boolean_query}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Build references in semantic mode (triggers boolean generation)
    print("\n[TEST 2] Build references in semantic mode:")
    try:
        csv_path = await service.build_references(
            query="renewable energy subsidies impact",
            sources=["openalex"],  # Just use OpenAlex to keep it simple
            limit=5,
            mode="semantic",
        )
        print(f"Created references CSV at: {csv_path}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 3: Build references in boolean mode (no generation)
    print("\n[TEST 3] Build references in boolean mode:")
    try:
        csv_path = await service.build_references(
            query="climate AND adaptation",
            sources=["openalex"],
            limit=5,
            mode="boolean",
            boolean_query="climate AND adaptation AND urban",
        )
        print(f"Created references CSV at: {csv_path}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("✅ Debug logging test complete!")
    print("Check the log messages above to see the debug output.")


if __name__ == "__main__":
    asyncio.run(test_debug_logging())
