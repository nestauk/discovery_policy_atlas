"""
Class for testing boolean query generation with different prompts and query backends.

Usage (run from backend directory):
    cd backend
    uv run python testing/r_and_d/boolean_queries/test_baseline.py
    
Or in code:
    tester = BooleanQueryTester(
        research_questions=["What is the biggest intervention for decarbonising home heating?"],
        config_path="testing/r_and_d/boolean_queries/config.yaml",
        prompt_generators={
            "generate_with_llm": generate_with_llm,
            "use_baseline_query": use_baseline_query,
        },
        query_function=query_openalex_minimal,
        system_prompts={"prompt_name": prompt_text},
    )
"""

import time
import yaml
import asyncio
import pandas as pd
import json
import logging
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

from app.core.config import settings  # noqa: E402
from app.services.openalex import OpenAlexService  # noqa: E402
from app.services.openalex import sanitize_openalex_query  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Reference queries (relative to this file)
reference_path = Path(__file__).parent / "inputs/reference_queries.csv"
reference_df = pd.read_csv(reference_path)
reference_question_to_query = dict(
    zip(reference_df["question"], reference_df["boolean_query"])
)


def get_question_id(question: str) -> str:
    """Get the question ID from the reference queries CSV."""
    return reference_df[reference_df["question"] == question]["identifier"].values[0]


# ============================================================================
# PROMPT GENERATION FUNCTIONS
# ============================================================================


async def generate_with_llm(
    question: str,
    model: str,
    temperature: float,
    system_prompt: str,
    client: AsyncOpenAI = AsyncOpenAI(api_key=settings.OPENAI_API_KEY),
    max_tokens: int = None,
) -> str:
    """Generate boolean query using an LLM with the given prompt and parameters."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    # Support legacy models that expect no explicit system role
    if model in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
        )
    else:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return resp.choices[0].message.content.strip()


async def use_baseline_query(
    question: str,
    model: str,
    temperature: float,
    system_prompt: str,
    client: AsyncOpenAI = AsyncOpenAI(api_key=settings.OPENAI_API_KEY),
    *args,
    **kwargs,
) -> str:
    """Return pre-existing baseline boolean query (no generation).

    Args:
        baseline_query: The pre-existing boolean query to use
        Other params are ignored but kept for signature compatibility
    """
    if question in reference_question_to_query:
        return reference_question_to_query[question]
    else:
        raise ValueError(f"Question {question} not found in reference queries")


# ============================================================================
# QUERY EXECUTION FUNCTIONS
# ============================================================================


async def query_openalex_minimal(
    query: str,
    count_only: bool = False,
) -> Tuple[pd.DataFrame, Optional[int]] | int:
    """Execute query against OpenAlex using minimal search.

    Args:
        query: Boolean query string
        count_only: If True, only return the total count without fetching results

    Returns:
        If count_only=True: int (total count)
        If count_only=False: Tuple[pd.DataFrame, int] (results dataframe, total count)
    """
    openalex_service = OpenAlexService()
    if count_only:
        return await openalex_service.search_minimal(
            query=query,
            count_only=True,
        )
    else:
        return await openalex_service.search_minimal(
            query=query,
            max_results=None,
            min_citations=0,
            return_n_total=True,
        )


class BooleanQueryTester:
    """Run boolean query generation experiments with pluggable prompts and query backends.

    This concurrent version runs multiple experiments in parallel with configurable concurrency limit.

    Inputs:
        research_questions: list of research questions
        config_path: YAML with iteration params (e.g., models, temperatures, prompts, max_concurrent).
        prompt_generators: Dict mapping generator names to generator functions.
            Signature: async fn(question, model, temperature, system_prompt, client, **kwargs) -> str
        query_function: Query execution function.
            Signature: async fn(query: str) -> Tuple[pd.DataFrame, Optional[int]]
        system_prompts: Dict mapping prompt names to prompt text strings
    """

    def __init__(
        self,
        research_questions: list[str],
        config_path: str | Path,
        prompt_generators: Dict[str, Callable],
        query_function: Callable,
        system_prompts: Dict[str, str],
    ) -> None:
        self.research_questions = research_questions
        with open(config_path, "r") as f:
            self.config = yaml.load(f, Loader=yaml.SafeLoader)
        self.openalex = OpenAlexService()
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        self.prompt_generators = prompt_generators
        self.query_function = query_function
        self.system_prompts = system_prompts

        # Concurrency control
        max_concurrent = self.config.get("max_concurrent", 10)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.file_lock = asyncio.Lock()

    @staticmethod
    def _query_lengths(query: str) -> Tuple[int, int]:
        # Approximate token count by whitespace split; element count by boolean term segmentation
        n_tokens = len(query.split())
        normalized = (
            query.replace("(", " ")
            .replace(")", " ")
            .replace("AND", "|")
            .replace("OR", "|")
            .replace("NOT", "|")
        )
        parts = [p.strip() for p in normalized.split("|") if p.strip()]
        n_elements = len(parts)
        return n_tokens, n_elements

    @staticmethod
    def _recall_metrics(
        retrieved_ids: set, baseline_ids: Optional[set]
    ) -> Tuple[Optional[float], Optional[float], int, int, int]:
        if not baseline_ids:
            return None, None, len(retrieved_ids), 0, 0
        overlap = len(retrieved_ids & baseline_ids)
        retrieved = len(retrieved_ids)
        baseline = len(baseline_ids)
        overlap_pct = (overlap / retrieved) * 100.0 if retrieved > 0 else 0.0
        total_recall = (overlap / baseline) * 100.0 if baseline > 0 else 0.0
        return overlap_pct, total_recall, retrieved, baseline, overlap

    async def _run_single_experiment(
        self,
        question: str,
        generator_name: str,
        prompt_name: str,
        model: str,
        temperature: float,
        run: int,
        count_only: bool,
        results_fh: Optional[Any],
    ) -> Dict[str, Any]:
        """Run a single experiment with semaphore control."""
        async with self.semaphore:
            logger.info(
                f"Running experiment: {question}|{generator_name}|{prompt_name}|{model}|{temperature}|run_{run}"
            )

            # Initialize result record with defaults
            result_record = {
                "question": question,
                "generator": generator_name,
                "prompt": prompt_name,
                "model": model,
                "temperature": temperature,
                "run": run,
                "error": None,
                "error_stage": None,
            }

            try:
                # Generate boolean query
                t0 = time.perf_counter()

                boolean_query = await self.prompt_generators[generator_name](
                    question=question,
                    model=model,
                    temperature=temperature,
                    system_prompt=self.system_prompts[prompt_name],
                    client=self.client,
                )
                boolean_query = sanitize_openalex_query(boolean_query)
                t1 = time.perf_counter()

                result_record.update(
                    {
                        "boolean_query": boolean_query,
                        "n_tokens": len(boolean_query.split()),
                        "n_elements": self._query_lengths(boolean_query)[1],
                        "llm_latency_s": t1 - t0,
                    }
                )

                try:
                    # Execute query
                    if count_only:
                        n_total = await self.query_function(
                            boolean_query, count_only=True
                        )
                        n_retrieved = n_total  # For count_only, they're the same
                        df = None
                    else:
                        df, n_total = await self.query_function(
                            boolean_query, count_only=False
                        )
                        retrieved_ids = set(df["id"].dropna().astype(str).tolist())
                        n_retrieved = len(retrieved_ids)

                    t2 = time.perf_counter()

                    result_record.update(
                        {
                            "query_latency_s": t2 - t1,
                            "retrieved_count": n_retrieved,
                            "retrieved_total": n_total,
                        }
                    )

                    # Add result details only if not count_only
                    if not count_only and df is not None:
                        result_record.update(
                            {
                                "results_id": list(retrieved_ids),
                                "results_doi": df["doi"].dropna().astype(str).tolist(),
                                "results_title": df["title"]
                                .dropna()
                                .astype(str)
                                .tolist(),
                                "results_cited_by_count": df["cited_by_count"]
                                .dropna()
                                .astype(int)
                                .tolist(),
                            }
                        )

                except Exception as e:
                    # Query execution failed
                    logger.error(f"Query execution failed: {str(e)[:200]}")
                    result_record.update(
                        {
                            "error": str(e)[:500],  # Truncate to 500 chars
                            "error_stage": "query_execution",
                            "query_latency_s": None,
                            "retrieved_count": None,
                            "retrieved_total": None,
                        }
                    )

            except Exception as e:
                # Query generation failed
                logger.error(f"Query generation failed: {str(e)[:200]}")
                result_record.update(
                    {
                        "error": str(e)[:500],  # Truncate to 500 chars
                        "error_stage": "query_generation",
                        "boolean_query": None,
                        "n_tokens": None,
                        "n_elements": None,
                        "llm_latency_s": None,
                        "query_latency_s": None,
                        "retrieved_count": None,
                        "retrieved_total": None,
                    }
                )

            # Write to file immediately if provided (thread-safe)
            if results_fh:
                async with self.file_lock:
                    results_fh.write(json.dumps(result_record) + "\n")
                    results_fh.flush()

            return result_record

    async def run(
        self,
        generator_names: Optional[List[str]] = None,
        prompt_names: Optional[List[str]] = None,
        results_file: Optional[Path | str] = None,
        count_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run experiments across generators, prompts, models, and temperatures.

        Args:
            generator_names: Names of generator functions to use (e.g., ["generate_with_llm", "use_baseline_query"])
            prompt_names: Names of system prompts to use (e.g., ["policy_atlas_v2"])
            results_file: Optional path to save results incrementally in JSONL format.
                         Creates new file or appends to existing file.
            count_only: If True, only retrieve counts without fetching full results (faster)

        Returns:
            List of result dictionaries
        """
        models = self.config.get("models")
        temperatures = self.config.get("temperatures")
        runs_per_query = self.config.get(
            "runs_per_query", 1
        )  # Default to 1 if not specified

        # Default to all registered generators if not specified
        generator_names = generator_names or list(self.prompt_generators.keys())
        # Default to all registered prompts if not specified
        prompt_names = prompt_names or list(self.system_prompts.keys())

        results_records: List[Dict[str, Any]] = []

        logger.info(f"Runs per query: {runs_per_query}")

        # Load existing results to avoid duplicates
        existing_keys = set()
        if results_file:
            results_path = Path(results_file)
            if results_path.exists():
                logger.info(f"Loading existing results from: {results_path}")
                with open(results_path, "r") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            # Create key from parameters
                            key = (
                                record.get("question"),
                                record.get("generator"),
                                record.get("prompt"),
                                record.get("model"),
                                record.get("temperature"),
                                record.get("run"),
                            )
                            existing_keys.add(key)
                        except json.JSONDecodeError:
                            continue
                logger.info(
                    f"Found {len(existing_keys)} existing results, will skip duplicates"
                )

        # Open results file for appending
        results_fh = None
        if results_file:
            results_path = Path(results_file)
            results_path.parent.mkdir(parents=True, exist_ok=True)
            results_fh = open(results_path, "a")
            logger.info(f"Saving results to: {results_path}")

        n_skipped = 0

        try:
            # Collect all experiment tasks
            tasks = []
            for question in self.research_questions:
                for generator_name in generator_names:
                    for prompt_name in prompt_names:
                        for model in models:
                            # GPT-5 models don't use temperature, so only run once
                            is_gpt5_model = model in [
                                "gpt-5",
                                "gpt-5-mini",
                                "gpt-5-nano",
                            ]
                            temps_to_use = (
                                temperatures[:1] if is_gpt5_model else temperatures
                            )

                            for temperature in temps_to_use:
                                for run in range(1, runs_per_query + 1):
                                    # Check if this combination already exists
                                    experiment_key = (
                                        question,
                                        generator_name,
                                        prompt_name,
                                        model,
                                        temperature,
                                        run,
                                    )
                                    if experiment_key in existing_keys:
                                        logger.debug(
                                            f"Skipping (already exists): {question}|{generator_name}|{prompt_name}|{model}|{temperature}|run_{run}"
                                        )
                                        n_skipped += 1
                                        continue

                                    # Create task for this experiment
                                    task = self._run_single_experiment(
                                        question=question,
                                        generator_name=generator_name,
                                        prompt_name=prompt_name,
                                        model=model,
                                        temperature=temperature,
                                        run=run,
                                        count_only=count_only,
                                        results_fh=results_fh,
                                    )
                                    tasks.append(task)

            n_total_experiments = len(tasks)
            logger.info(
                f"Running {n_total_experiments} experiments concurrently (max {self.config.get('max_concurrent', 10)} at once)"
            )

            # Run all tasks concurrently
            results_records = await asyncio.gather(*tasks)

        finally:
            # Close file handle if opened
            if results_fh:
                results_fh.close()
                logger.info("Results file closed")

        # Log summary
        n_processed = len(results_records)
        if n_skipped > 0:
            logger.info(
                f"Skipped {n_skipped} existing results, processed {n_processed} new experiments"
            )
        else:
            logger.info(f"Processed {n_processed} experiments")

        return list(results_records)
