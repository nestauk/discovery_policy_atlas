"""
Test script for the complete Analysis Service pipeline including relevance checking.

Tests the full end-to-end flow:
1. References retrieval from OpenAlex/Overton
2. Relevance checking and document type classification
3. Document acquisition (filtered to relevant documents)
4. Parsing and normalization
5. LangChain extraction workflow
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add the backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.analysis.service import AnalysisService
from app.services.analysis.schemas import RunConfig


async def test_full_analysis_pipeline():
    """Test the complete analysis pipeline with relevance checking."""
    print("🧪 Testing Full Analysis Pipeline")
    print("=" * 50)

    # Configuration for the test
    config = RunConfig(
        # query="(parenting) AND (intervention) AND (rct OR \"controlled trial\")",
        query="Reducing electricity prices for customers, focussing on low-income households",
        sources=["openalex", "overton"],
        limit=5,  # Small limit for testing
        relevance_enabled=True,  # Test the new relevance feature
        retrieval_mode="semantic",
        use_abstracts_only=False,  # Test full document processing
    )

    print("📋 Test Configuration:")
    print(f"   Query: {config.query}")
    print(f"   Sources: {config.sources}")
    print(f"   Limit: {config.limit}")
    print(f"   Relevance Enabled: {config.relevance_enabled}")
    print(f"   Mode: {config.retrieval_mode}")
    print(f"   Use Abstracts Only: {config.use_abstracts_only}")

    # Create analysis service with test directory
    test_export_dir = Path("backend/temp/test_analysis")
    test_export_dir.mkdir(parents=True, exist_ok=True)

    analysis_service = AnalysisService(export_dir=str(test_export_dir))

    try:
        print("\n🚀 Starting analysis pipeline...")
        start_time = datetime.now()

        result = await analysis_service.run(config)

        end_time = datetime.now()
        duration = end_time - start_time

        print(f"\n✅ Analysis completed in {duration.total_seconds():.1f} seconds")
        print("📊 Results Summary:")
        print(f"   Run ID: {result.run_id}")
        print(f"   Total References Found: {result.total_references}")

        if result.relevant_references is not None:
            print(f"   Relevant References: {result.relevant_references}")
            relevance_rate = (
                (result.relevant_references / result.total_references * 100)
                if result.total_references > 0
                else 0
            )
            print(f"   Relevance Rate: {relevance_rate:.1f}%")

        print(f"   References CSV: {result.references_csv_path}")

        if result.extractions_json_path:
            print(f"   Extractions JSON: {result.extractions_json_path}")

        # Analyze the references CSV to see relevance results
        await analyze_relevance_results(result.references_csv_path)

        # Analyze extractions if available
        if result.extractions_json_path:
            await analyze_extraction_results_consolidated(result.extractions_json_path)

        return result

    except Exception as e:
        print(f"❌ Analysis pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        raise


async def analyze_relevance_results(references_csv_path: str):
    """Analyze the relevance checking results."""
    print("\n🔍 Analyzing Relevance Results")
    print("-" * 30)

    try:
        import pandas as pd

        df = pd.read_csv(references_csv_path)

        if "is_relevant" not in df.columns:
            print("⚠️  No relevance data found in references CSV")
            return

        print(f"📄 Total Documents: {len(df)}")

        # Relevance statistics
        relevant_docs = df[df["is_relevant"] == True]
        print(f"✅ Relevant Documents: {len(relevant_docs)}")

        if "relevance_confidence" in df.columns:
            avg_confidence = df["relevance_confidence"].mean()
            print(f"📊 Average Confidence: {avg_confidence:.2f}")

        # Document type breakdown
        if "document_type" in df.columns:
            doc_types = df["document_type"].value_counts()
            print("📋 Document Types:")
            for doc_type, count in doc_types.items():
                print(f"   - {doc_type}: {count}")

        # Show some examples
        if len(relevant_docs) > 0:
            print("\n📝 Sample Relevant Documents:")
            for idx, (_, row) in enumerate(relevant_docs.head(3).iterrows()):
                print(f"   {idx + 1}. {row.get('title', 'No title')[:80]}...")
                if "top_line" in row and pd.notna(row["top_line"]):
                    print(f"      Summary: {row['top_line']}")
                if "document_type" in row and pd.notna(row["document_type"]):
                    print(f"      Type: {row['document_type']}")
                if "relevance_reason" in row and pd.notna(row["relevance_reason"]):
                    print(f"      Reason: {row['relevance_reason'][:100]}...")
                print()

    except Exception as e:
        print(f"❌ Failed to analyze relevance results: {e}")


async def analyze_extraction_results_consolidated(extractions_json_path: str):
    """Analyze the consolidated extraction results."""
    print("\n🔬 Analyzing Consolidated Extraction Results")
    print("-" * 40)

    try:
        with open(extractions_json_path, "r") as f:
            consolidated_data = json.load(f)

        metadata = consolidated_data.get("run_metadata", {})
        extractions = consolidated_data.get("extractions", [])

        print("📊 Consolidated Extraction Summary:")
        print(f"   Total Documents: {metadata.get('total_documents', 0)}")
        print(f"   Processed Documents: {metadata.get('processed_documents', 0)}")
        print(f"   Use Abstracts Only: {metadata.get('use_abstracts_only', False)}")
        print(f"   Model: {metadata.get('model', 'Unknown')}")

        if len(extractions) == 0:
            print("⚠️  No extractions found")
            return

        # Aggregate statistics
        total_issues = sum(len(ext.get("issues", [])) for ext in extractions)
        total_interventions = sum(
            len(ext.get("interventions", [])) for ext in extractions
        )
        total_results = sum(len(ext.get("results", [])) for ext in extractions)

        print("\n📈 Aggregated Results:")
        print(f"   Total Issues: {total_issues}")
        print(f"   Total Interventions: {total_interventions}")
        print(f"   Total Results: {total_results}")

        # Show sample extraction
        sample_extraction = extractions[0]
        print(
            f"\n📋 Sample Extraction ({sample_extraction.get('paper_id', 'Unknown')}):"
        )

        # Check text source metadata
        if "extraction_metadata" in sample_extraction:
            meta = sample_extraction["extraction_metadata"]
            print(f"   File Size: {meta.get('file_size_bytes', 0)} bytes")
            print(f"   Processed At: {meta.get('processed_at', 'Unknown')}")

        if "issues" in sample_extraction:
            issues = sample_extraction["issues"]
            print(f"   Issues Found: {len(issues)}")
            for i, issue in enumerate(issues[:2]):  # Show first 2
                print(f"      {i+1}. {issue.get('label', 'No label')}")

        if "interventions" in sample_extraction:
            interventions = sample_extraction["interventions"]
            print(f"   Interventions Found: {len(interventions)}")
            for i, intervention in enumerate(interventions[:2]):  # Show first 2
                print(
                    f"      {i+1}. {intervention.get('name', 'No name')} ({intervention.get('type', 'No type')})"
                )

        if "results" in sample_extraction:
            results = sample_extraction["results"]
            print(f"   Results Found: {len(results)}")
            for i, result in enumerate(results[:2]):  # Show first 2
                outcome = result.get("outcome_variable", "No outcome")
                direction = result.get("effect_direction", "No direction")
                print(f"      {i+1}. {outcome}: {direction}")

        if "conclusion" in sample_extraction and sample_extraction["conclusion"]:
            conclusion = sample_extraction["conclusion"]
            summary = conclusion.get("top_line_summary", "No summary")
            print(f"   Conclusion: {summary}")

    except Exception as e:
        print(f"❌ Failed to analyze consolidated extraction results: {e}")


async def test_relevance_only():
    """Test just the relevance checking functionality."""
    print("\n🎯 Testing Relevance Checking Only")
    print("=" * 40)

    config = RunConfig(
        query='(parenting) AND (intervention) AND (rct OR "controlled trial")',
        sources=["openalex"],  # Just OpenAlex for speed
        limit=10,  # Slightly more documents for relevance testing
        relevance_enabled=True,
        use_abstracts_only=True,  # Skip full document processing
    )

    test_export_dir = Path("backend/temp/test_relevance_only")
    test_export_dir.mkdir(parents=True, exist_ok=True)

    analysis_service = AnalysisService(export_dir=str(test_export_dir))

    try:
        print("🚀 Starting relevance-only test...")
        result = await analysis_service.run(config)

        print("✅ Relevance test completed")
        print(f"   Total: {result.total_references}")
        print(f"   Relevant: {result.relevant_references}")

        await analyze_relevance_results(result.references_csv_path)

        return result

    except Exception as e:
        print(f"❌ Relevance test failed: {e}")
        raise


if __name__ == "__main__":
    print("🚀 Testing Analysis Service with Relevance Pipeline")
    print("=" * 60)

    # Check requirements
    if not settings.OPENAI_API_KEY:
        print(
            "❌ OPENAI_API_KEY not set in settings. Please configure your environment."
        )
        print("   You can set it in your environment variables or .env file")
        exit(1)

    print("✅ OPENAI_API_KEY is configured")

    # Test 1: Relevance checking only (faster)
    print("\n1️⃣  Testing Relevance Checking Only...")
    try:
        asyncio.run(test_relevance_only())
    except Exception as e:
        print(f"❌ Relevance test failed: {e}")

    # Test 2: Full pipeline (slower but comprehensive)
    print("\n2️⃣  Testing Full Analysis Pipeline...")
    try:
        asyncio.run(test_full_analysis_pipeline())
    except Exception as e:
        print(f"❌ Full pipeline test failed: {e}")

    print("\n🎉 All tests completed!")
    print("\nTo run just the relevance test (faster):")
    print(
        "   python -c 'import asyncio; from test_analysis_service import test_relevance_only; asyncio.run(test_relevance_only())'"
    )
    print("\nTo run the full pipeline test:")
    print(
        "   python -c 'import asyncio; from test_analysis_service import test_full_analysis_pipeline; asyncio.run(test_full_analysis_pipeline())'"
    )
