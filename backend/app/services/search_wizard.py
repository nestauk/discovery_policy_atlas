"""
Search wizard service for generating population and outcome options.

Provides LLM-powered generation of relevant population and outcome options
for research questions, ordered from broad to narrow.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.services.analysis.prompts import (
    POPULATION_OPTIONS_SYSTEM_PROMPT,
    OUTCOME_OPTIONS_SYSTEM_PROMPT,
    ADDITIONAL_QUESTIONS_SYSTEM_PROMPT,
)
from app.utils.llm.llm_utils import (
    resolve_langfuse_session_id,
    get_langfuse_handler,
    build_langfuse_metadata,
)


logger = logging.getLogger(__name__)


class SearchWizardService:
    """Service for generating search wizard options using LLM."""

    def __init__(self):
        """Initialize the search wizard service."""
        pass

    async def generate_population_options(
        self,
        research_question: str,
        max_options: int = 3,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[str]:
        """
        Generate population options for a research question, ordered from broad to narrow.

        Args:
            research_question: The research question to generate options for
            max_options: Maximum number of options to generate (default: 3)
            project_id: Optional project ID for Langfuse tracking
            user_id: Optional user ID for Langfuse tracking

        Returns:
            List of population options ordered from broad to narrow
        """
        logger.info("🔍 Generating population options for: '%s'", research_question)

        try:
            # Initialize Langfuse handler for tracking
            session_id = resolve_langfuse_session_id(project_id)
            langfuse_handler = get_langfuse_handler(session_id=session_id)

            # Create LLM instance
            llm = ChatOpenAI(
                model=settings.SEARCH_WIZARD_MODEL,
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=300,
            )

            messages = [
                SystemMessage(content=POPULATION_OPTIONS_SYSTEM_PROMPT),
                HumanMessage(content=f"Research question: {research_question}"),
            ]

            # Build config with callbacks and metadata
            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:search_wizard",
                        "component:search_wizard.population_options",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "search_wizard.population_options"

            resp = await llm.ainvoke(messages, config=config)
            content = (resp.content or "").strip()

            if not content:
                logger.warning("❌ No response from AI for population options")
                return []

            # Parse the JSON array
            try:
                population_options = json.loads(content)
                if not isinstance(population_options, list):
                    raise ValueError("Expected JSON array")

                # Limit to requested number and ensure they're strings
                population_options = [
                    str(opt).strip() for opt in population_options[:max_options] if opt
                ]

                logger.info(
                    "✅ Generated %d population options", len(population_options)
                )
                return population_options

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse AI response as JSON: {content}")
                logger.error(f"Parse error: {e}")
                return []

        except Exception as e:
            logger.error(f"Error generating population options: {e}")
            return []

    async def generate_outcome_options(
        self,
        research_question: str,
        max_options: int = 3,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[str]:
        """
        Generate outcome options for a research question, ordered from broad to narrow.

        Args:
            research_question: The research question to generate options for
            max_options: Maximum number of options to generate (default: 3)
            project_id: Optional project ID for Langfuse tracking
            user_id: Optional user ID for Langfuse tracking

        Returns:
            List of outcome options ordered from broad to narrow
        """
        logger.info("🔍 Generating outcome options for: '%s'", research_question)

        try:
            # Initialize Langfuse handler for tracking
            session_id = resolve_langfuse_session_id(project_id)
            langfuse_handler = get_langfuse_handler(session_id=session_id)

            # Create LLM instance
            llm = ChatOpenAI(
                model=settings.SEARCH_WIZARD_MODEL,
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=300,
            )

            messages = [
                SystemMessage(content=OUTCOME_OPTIONS_SYSTEM_PROMPT),
                HumanMessage(content=f"Research question: {research_question}"),
            ]

            # Build config with callbacks and metadata
            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:search_wizard",
                        "component:search_wizard.outcome_options",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "search_wizard.outcome_options"

            resp = await llm.ainvoke(messages, config=config)
            content = (resp.content or "").strip()

            if not content:
                logger.warning("❌ No response from AI for outcome options")
                return []

            # Parse the JSON array
            try:
                outcome_options = json.loads(content)
                if not isinstance(outcome_options, list):
                    raise ValueError("Expected JSON array")

                # Limit to requested number and ensure they're strings
                outcome_options = [
                    str(opt).strip() for opt in outcome_options[:max_options] if opt
                ]

                logger.info("✅ Generated %d outcome options", len(outcome_options))
                return outcome_options

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse AI response as JSON: {content}")
                logger.error(f"Parse error: {e}")
                return []

        except Exception as e:
            logger.error(f"Error generating outcome options: {e}")
            return []

    async def generate_additional_questions(
        self,
        research_question: str,
        population_selected: List[str],
        outcome_selected: List[str],
        max_questions: int = 2,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[str]:
        """
        Generate additional research questions based on the main question, population, and outcome.

        Args:
            research_question: The main research question
            population_selected: List of selected population interests
            outcome_selected: List of selected outcome interests
            max_questions: Maximum number of questions to generate (default: 2)
            project_id: Optional project ID for Langfuse tracking
            user_id: Optional user ID for Langfuse tracking

        Returns:
            List of additional research questions
        """
        logger.info("🔍 Generating additional questions for: '%s'", research_question)

        try:
            # Initialize Langfuse handler for tracking
            session_id = resolve_langfuse_session_id(project_id)
            langfuse_handler = get_langfuse_handler(session_id=session_id)

            # Create LLM instance
            llm = ChatOpenAI(
                model=settings.SEARCH_WIZARD_MODEL,
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY,
                max_tokens=300,
            )

            # Build context message
            context_parts = [f"Research question: {research_question}"]
            if population_selected:
                context_parts.append(
                    f"Population interests: {', '.join(population_selected)}"
                )
            if outcome_selected:
                context_parts.append(
                    f"Outcome interests: {', '.join(outcome_selected)}"
                )

            messages = [
                SystemMessage(content=ADDITIONAL_QUESTIONS_SYSTEM_PROMPT),
                HumanMessage(content="\n".join(context_parts)),
            ]

            # Build config with callbacks and metadata
            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = build_langfuse_metadata(
                    tags=[
                        "component:search_wizard",
                        "component:search_wizard.additional_questions",
                    ],
                    session_id=session_id,
                    user_id=user_id,
                    project_id=project_id,
                )
                config["run_name"] = "search_wizard.additional_questions"

            resp = await llm.ainvoke(messages, config=config)
            content = (resp.content or "").strip()

            if not content:
                logger.warning("❌ No response from AI for additional questions")
                return []

            # Parse the JSON array
            try:
                additional_questions = json.loads(content)
                if not isinstance(additional_questions, list):
                    raise ValueError("Expected JSON array")

                # Limit to requested number and ensure they're strings
                additional_questions = [
                    str(q).strip() for q in additional_questions[:max_questions] if q
                ]

                logger.info(
                    "✅ Generated %d additional questions", len(additional_questions)
                )
                return additional_questions

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse AI response as JSON: {content}")
                logger.error(f"Parse error: {e}")
                return []

        except Exception as e:
            logger.error(f"Error generating additional questions: {e}")
            return []
