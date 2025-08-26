"""
Simple test script for the LangChain/LangGraph extraction workflow.
"""

import asyncio
from pathlib import Path

from app.core.config import settings
from ..app.services.analysis.extractor_langchain import (
    LangChainExtractorService,
    LangChainExtractionConfig,
)
from ..app.services.analysis.workflow_langchain import ExtractionWorkflow


async def test_workflow_simple():
    """Test the workflow with a real research paper."""
    # Load the real autism research paper
    paper_path = Path("temp/data/normalized/doi.org_10.1136_bmj.39126.620799.55.txt")

    if not paper_path.exists():
        print(f"❌ Paper file not found: {paper_path}")
        print("   Please ensure the file exists or adjust the path")
        return None

    real_paper = paper_path.read_text(encoding="utf-8", errors="ignore")
    print(f"📄 Loaded real paper: {len(real_paper)} characters")
    print(f"📄 First 200 chars: {real_paper[:200]}...")

    # Test the workflow
    workflow = ExtractionWorkflow()
    result = await workflow.run("doi.org_10.1016_j.jaac.2012.08.003", real_paper)

    print("🧪 Test Results:")
    print(f"Paper ID: {result.paper_id}")
    print(f"Issues: {len(result.issues)}")
    for issue in result.issues:
        print(f"  - {issue.label}")

    print(f"Interventions: {len(result.interventions)}")
    for intervention in result.interventions:
        print(f"  - {intervention.name} ({intervention.type})")

    print(f"Mappings: {len(result.mappings)}")
    for mapping in result.mappings:
        print(
            f"  - Issue {mapping.issue_idx} → Intervention {mapping.intervention_idx}"
        )

    print(f"Results: {len(result.results)}")
    for res in result.results:
        print(f"  - {res.outcome_variable}: {res.effect_direction}")

    if result.conclusion:
        print("Conclusion:")
        print(f"  - Summary: {result.conclusion.top_line_summary}")
    else:
        print("Conclusion: None extracted")

    # Save detailed output
    output_path = Path("real_paper_extraction_output.json")
    output_path.write_text(result.model_dump_json(indent=2))
    print(f"\n📁 Detailed output saved to: {output_path}")

    return result


async def test_extractor_service():
    """Test the full extractor service with existing temp data."""
    # Check if we have some test data
    temp_dir = Path("backend/temp")
    if not temp_dir.exists():
        print("⚠️  No temp directory found for testing")
        return

    # Look for test data
    csv_files = list(temp_dir.glob("**/references.csv"))
    if not csv_files:
        print("⚠️  No references.csv found in temp directory")
        return

    references_csv = csv_files[0]
    normalized_dir = references_csv.parent / "data" / "normalized"

    if not normalized_dir.exists():
        print(f"⚠️  No normalized directory found at {normalized_dir}")
        return

    print(f"🧪 Testing with data from: {references_csv.parent}")

    # Configure extractor
    config = LangChainExtractionConfig(
        run_id="test_langchain",
        export_dir=str(references_csv.parent / "langchain_test"),
        use_abstracts_only=True,  # Use abstracts only for quick testing
        concurrency=1,  # Low concurrency for testing
    )

    extractor = LangChainExtractorService(config)

    # Run extraction on a few documents
    try:
        extractions_dir = await extractor.extract_for_documents(
            str(references_csv), str(normalized_dir)
        )

        print(f"✅ Extractions completed, output in: {extractions_dir}")

        # Convert to CSVs
        csv_files = extractor.write_csvs(str(references_csv), str(extractions_dir))
        print("✅ CSV files created:")
        for csv_type, csv_path in csv_files.items():
            print(f"  - {csv_type}: {csv_path}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    print("🚀 Testing LangChain/LangGraph Extraction Workflow")
    print("=" * 50)

    # Check if we have an OpenAI API key
    if not settings.OPENAI_API_KEY:
        print(
            "❌ OPENAI_API_KEY not set in settings. Please configure your environment."
        )
        print("   You can set it in your environment variables or .env file")
        exit(1)

    print(f"✅ OPENAI_API_KEY is configured (length: {len(settings.OPENAI_API_KEY)})")

    # Test 1: Simple workflow test
    print("\n1️⃣  Testing workflow with mock paper...")
    asyncio.run(test_workflow_simple())

    # Test 2: Full extractor service test
    print("\n2️⃣  Testing extractor service with real data...")
    asyncio.run(test_extractor_service())

    print("\n✅ All tests completed!")
