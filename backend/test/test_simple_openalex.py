#!/usr/bin/env python3
"""
Simple test script for OpenAlex querying through the analysis service.
Tests the ReferencesService with minimal configuration.
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.analysis.references import ReferencesService


async def test_simple_openalex():
    """Test OpenAlex querying with a simple query."""
    print("🧪 Testing Simple OpenAlex Query")
    print("=" * 40)

    # Create a simple test directory
    test_dir = Path("temp/test_simple_openalex")
    test_dir.mkdir(parents=True, exist_ok=True)

    # Initialize the references service
    references_service = ReferencesService(export_dir=str(test_dir))

    # Simple test configuration
    query = "climate change"
    sources = ["openalex"]  # Only test OpenAlex
    limit = 3  # Keep it very small

    print(f"Query: '{query}'")
    print(f"Sources: {sources}")
    print(f"Limit: {limit}")
    print(f"Export dir: {test_dir}")
    print()

    try:
        print("🚀 Starting OpenAlex search...")

        # Test the build_references method
        references_csv_path = await references_service.build_references(
            query=query,
            sources=sources,
            limit=limit,
            mode="semantic",  # Use semantic mode to test boolean query generation
        )

        print("✅ Search completed successfully!")
        print(f"📄 References CSV: {references_csv_path}")

        # Check if files were created
        if references_csv_path.exists():
            print(f"✅ References CSV file created: {references_csv_path}")

            # Read and display basic stats
            import pandas as pd

            df = pd.read_csv(references_csv_path)
            print(f"📊 Found {len(df)} references")

            if len(df) > 0:
                print(f"📚 First result title: {df.iloc[0]['title']}")
                print(f"🏷️  Sources found: {df['source'].unique().tolist()}")
            else:
                print("⚠️  No references found in CSV")
        else:
            print(f"❌ References CSV file not created: {references_csv_path}")

        # Check debug files
        debug_dir = test_dir / "debug"
        if debug_dir.exists():
            print(f"🔍 Debug directory exists: {debug_dir}")

            openalex_debug = debug_dir / "openalex_raw.json"
            if openalex_debug.exists():
                print(f"✅ OpenAlex debug file created: {openalex_debug}")
                print(
                    f"📊 OpenAlex debug file size: {openalex_debug.stat().st_size} bytes"
                )
            else:
                print(f"❌ OpenAlex debug file missing: {openalex_debug}")
        else:
            print(f"❌ Debug directory not created: {debug_dir}")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


async def main():
    """Run the simple test."""
    print("🔬 Simple OpenAlex Analysis Service Test")
    print("=" * 50)

    success = await test_simple_openalex()

    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
