"""Simple test script to verify the categorization works."""

import asyncio
from pathlib import Path

import pandas as pd

from categorise_evidence import main


def create_test_data():
    """Create a small test dataset with clear examples"""
    test_documents = [
        {
            "doc_id": "test_1",
            "title": "A Systematic Review and Meta-Analysis of Childhood Obesity Interventions",
            "abstract_or_summary": "This systematic review synthesizes evidence from 45 randomized controlled trials examining the effectiveness of school-based obesity prevention programs. Using PRISMA guidelines, we conducted a meta-analysis with pooled effect sizes showing significant reductions in BMI (d=0.23, 95% CI 0.15-0.31). Heterogeneity was moderate (I²=45%).",
            "year": 2023,
            "document_type": "research_paper",
            "source": "openalex",
        },
        {
            "doc_id": "test_2",
            "title": "Effect of a School-Based Nutrition Program: A Randomized Controlled Trial",
            "abstract_or_summary": "We conducted a randomized controlled trial with 500 students assigned to treatment (n=250) or control (n=250) groups. The intervention group received daily nutritious meals for 6 months. Results showed significant reduction in obesity prevalence (p<0.01) with effect size of 0.45.",
            "year": 2022,
            "document_type": "research_paper",
            "source": "openalex",
        },
        {
            "doc_id": "test_3",
            "title": "Longitudinal Cohort Study of Diet and Obesity in Adolescents",
            "abstract_or_summary": "This observational cohort study followed 2,000 adolescents over 5 years to examine associations between dietary patterns and obesity. Cross-sectional analysis at baseline and longitudinal analysis revealed strong correlations between fast food consumption and BMI increase (r=0.42).",
            "year": 2021,
            "document_type": "research_paper",
            "source": "openalex",
        },
        {
            "doc_id": "test_4",
            "title": "Economic Modeling of Obesity Prevention Policy Scenarios",
            "abstract_or_summary": "We developed an agent-based computational model to simulate the impact of different obesity prevention policies over 20 years. The model projects that sugar tax implementation could reduce obesity prevalence by 15% by 2045 under optimistic scenarios.",
            "year": 2024,
            "document_type": "research_paper",
            "source": "openalex",
        },
        {
            "doc_id": "test_5",
            "title": "Government White Paper: National Strategy for Childhood Obesity Prevention",
            "abstract_or_summary": "This policy document synthesizes evidence from multiple systematic reviews, RCTs, and observational studies to recommend a comprehensive national strategy for childhood obesity prevention. Recommendations include regulatory changes, school nutrition standards, and community programs. Evidence quality assessment included.",
            "year": 2023,
            "document_type": "policy_document",
            "source": "overton",
        },
        {
            "doc_id": "test_6",
            "title": "Lived Experiences of Obesity: A Qualitative Interview Study",
            "abstract_or_summary": "Through in-depth semi-structured interviews with 30 participants, we explored the lived experiences of individuals with obesity. Thematic analysis revealed key themes around stigma, barriers to treatment access, and the role of social support. Focus groups confirmed these findings.",
            "year": 2022,
            "document_type": "research_paper",
            "source": "openalex",
        },
        {
            "doc_id": "test_7",
            "title": "Commentary: Rethinking Obesity Prevention in the Modern Era",
            "abstract_or_summary": "In this editorial commentary, I argue that current approaches to obesity prevention are insufficient. Drawing on my 30 years of clinical experience and reflecting on recent policy debates, I propose that we need a paradigm shift in how we conceptualize obesity as a public health challenge.",
            "year": 2024,
            "document_type": "other",
            "source": "openalex",
        },
    ]

    df = pd.DataFrame(test_documents)
    return df


async def run_test():
    """Run a quick test with sample data"""
    print("Creating test dataset...")

    # Create test data
    df = create_test_data()

    # Save to inputs directory
    test_input = Path(__file__).parent / "inputs" / "test_references.csv"
    test_output = Path(__file__).parent / "outputs" / "test_categorised.csv"

    test_input.parent.mkdir(parents=True, exist_ok=True)
    test_output.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(test_input, index=False)
    print(f"Test data saved to: {test_input}")
    print(f"Documents: {len(df)}")

    # Run categorization
    print("\nRunning categorization...")
    await main(
        input_csv=str(test_input),
        output_csv=str(test_output),
        model="gpt-4o-mini",
        temperature=0.0,
        batch_size=5,
        max_concurrent=3,
    )

    # Show results
    print("\nTest Results:")
    print("=" * 80)
    results = pd.read_csv(test_output)
    for _, row in results.iterrows():
        print(f"\nTitle: {row['title'][:60]}...")
        print(f"Category: {row['evidence_category']}")
        print(f"Confidence: {row['evidence_confidence']:.2f}")
        print(f"Reasoning: {row['category_reasoning']}")


if __name__ == "__main__":
    asyncio.run(run_test())
