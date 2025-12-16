"""Evidence categorization script - classifies documents into 9 evidence categories."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from tqdm import tqdm
from prompts import CLASSIFICATION_SYSTEM_PROMPT, CLASSIFICATION_USER_PROMPT

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _ensure_backend_on_path() -> None:
    """Ensure the backend package is importable when running as a script."""

    backend_dir = Path(__file__).resolve().parents[3]
    backend_path = str(backend_dir)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


class EvidenceClassification(BaseModel):
    """Structured output for evidence classification"""

    category: str = Field(
        description="One of: 'Systematic Review and Meta-Analysis', 'RCTs and Quasi-Experimental Studies', "
        "'Observational Research Studies', 'Modelling & Simulation', "
        "'Policy Syntheses & Guidance Documents', 'Qualitative & Contextual Evidence', "
        "'Expert Opinion and Commentary', 'Other (Non-evidence documents)', "
        "'Unknown / Insufficient information'"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0
    )
    reasoning: str = Field(
        description="Brief explanation (1-2 sentences) for the classification"
    )


class EvidenceCategorizer:
    """Service for categorizing documents into evidence hierarchy"""

    def __init__(
        self,
        model: str = "gpt-5-mini",
        temperature: float = 0.0,
        batch_size: int = 10,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.batch_size = batch_size
        _ensure_backend_on_path()
        from app.utils.llm.llm_utils import get_llm

        self.llm = get_llm(model_name=model, temperature=temperature)

        # Create structured output LLM
        self.structured_llm = self.llm.with_structured_output(
            EvidenceClassification, method="json_schema"
        )

        # Use custom prompts if provided, otherwise use defaults
        system = (
            system_prompt if system_prompt is not None else CLASSIFICATION_SYSTEM_PROMPT
        )
        user = user_prompt if user_prompt is not None else CLASSIFICATION_USER_PROMPT

        # Create prompt template
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("user", user),
            ]
        )

        # Create the chain
        self.chain = self.prompt | self.structured_llm

        logger.info(
            f"Initialized EvidenceCategorizer with model={model}, temperature={temperature}"
        )

    async def classify_document(
        self,
        title: str,
        abstract: str,
        source: str = "",
        doc_type: str = "",
        year: Optional[int] = None,
    ) -> EvidenceClassification:
        """Classify a single document"""
        try:
            result = await self.chain.ainvoke(
                {
                    "title": title or "No title",
                    "abstract": abstract or "No abstract",
                    "source": source or "Unknown",
                    "doc_type": doc_type or "Unknown",
                    "year": year or "Unknown",
                }
            )
            return result
        except Exception as e:
            logger.error(f"Error classifying document '{title[:50]}...': {e}")
            # Return default classification on error
            return EvidenceClassification(
                category="Expert Opinion and Commentary",
                confidence=0.0,
                reasoning=f"Error during classification: {str(e)}",
            )

    async def classify_batch(
        self, documents: list[dict], semaphore: asyncio.Semaphore
    ) -> list[EvidenceClassification]:
        """Classify a batch of documents with concurrency control"""

        async def classify_with_semaphore(doc):
            async with semaphore:
                return await self.classify_document(
                    title=doc.get("title", ""),
                    abstract=doc.get("abstract_or_summary", ""),
                    source=doc.get("source", ""),
                    doc_type=doc.get("document_type", ""),
                    year=doc.get("year"),
                )

        tasks = [classify_with_semaphore(doc) for doc in documents]
        return await asyncio.gather(*tasks)

    async def classify_dataframe(
        self, df: pd.DataFrame, max_concurrent: int = 5
    ) -> pd.DataFrame:
        """Classify all documents in a dataframe"""
        logger.info(f"Starting classification of {len(df)} documents")

        # Convert dataframe to list of dicts
        documents = df.to_dict("records")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        # Process in batches with progress bar
        all_results = []
        for i in tqdm(
            range(0, len(documents), self.batch_size), desc="Classifying documents"
        ):
            batch = documents[i : i + self.batch_size]
            results = await self.classify_batch(batch, semaphore)
            all_results.extend(results)

        # Add results to dataframe
        df["evidence_category"] = [r.category for r in all_results]
        df["evidence_confidence"] = [r.confidence for r in all_results]
        df["category_reasoning"] = [r.reasoning for r in all_results]

        logger.info("Classification complete")
        return df


async def main(
    input_csv: str,
    output_csv: str,
    model: str = "gpt-5-mini",
    temperature: float = 0.0,
    batch_size: int = 10,
    max_concurrent: int = 5,
):
    """Main function to categorize evidence from CSV"""

    input_path = Path(input_csv)
    output_path = Path(output_csv)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Reading input CSV from: {input_path}")

    # Read CSV
    df = pd.read_csv(input_path)
    logger.info(f"Loaded {len(df)} documents")

    # Initialize categorizer
    categorizer = EvidenceCategorizer(
        model=model, temperature=temperature, batch_size=batch_size
    )

    # Classify documents
    df_classified = await categorizer.classify_dataframe(
        df, max_concurrent=max_concurrent
    )

    # Save results
    logger.info(f"Saving results to: {output_path}")
    df_classified.to_csv(output_path, index=False)

    # Print summary statistics
    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)
    print(f"\nTotal documents classified: {len(df_classified)}")
    print("\nCategory distribution:")
    print(df_classified["evidence_category"].value_counts().to_string())
    print(f"\nAverage confidence: {df_classified['evidence_confidence'].mean():.3f}")
    print(
        f"Low confidence (<0.6) count: {len(df_classified[df_classified['evidence_confidence'] < 0.6])}"
    )
    print("\n" + "=" * 60)

    logger.info("Classification complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Categorize evidence documents into 9 hierarchical categories"
    )
    parser.add_argument(
        "--input", required=True, help="Path to input references.csv file"
    )
    parser.add_argument(
        "--output", required=True, help="Path to output categorised CSV file"
    )
    parser.add_argument(
        "--model", default="gpt-5-mini", help="LLM model to use (default: gpt-5-mini)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for LLM (default: 0.0)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for processing (default: 10)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent API calls (default: 5)",
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            input_csv=args.input,
            output_csv=args.output,
            model=args.model,
            temperature=args.temperature,
            batch_size=args.batch_size,
            max_concurrent=args.max_concurrent,
        )
    )
