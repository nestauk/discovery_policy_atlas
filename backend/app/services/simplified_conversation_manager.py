"""
Simplified LangChain-based conversation manager for policy research
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.core.config import settings
from app.utils.llm.llm_utils import get_langfuse_handler

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    REFINE = "refine"
    CHAT = "chat"


class ConversationAnalysis(BaseModel):
    """AI's self-assessment of conversation state"""

    current_state: ConversationState = Field(
        description="Current conversation state: 'refine' or 'chat'"
    )
    outcomes_defined: bool = Field(
        description="Whether user has clearly defined their desired policy outcomes"
    )
    scope_defined: bool = Field(
        description="Whether user has defined scope (demographics, geography, constraints)"
    )
    search_query: str = Field(
        description="Current search query based on conversation so far"
    )
    ready_to_search: bool = Field(
        description="Whether there's enough information to start searching for evidence"
    )
    next_question: Optional[str] = Field(
        description="Suggested follow-up question if more refinement needed"
    )
    reasoning: str = Field(description="Brief explanation of the assessment")


class SimplifiedConversationManager:
    """Simplified LangChain conversation manager with AI self-assessment"""

    def __init__(self):
        self.llm = None
        self.analyzer = None
        self.langfuse_handler = None

        if settings.OPENAI_API_KEY and not settings.MOCK_OPENAI:
            self.llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                openai_api_key=settings.OPENAI_API_KEY,
            )
            # Langfuse handler for chat sessions
            self.langfuse_handler = get_langfuse_handler(
                session_id=f"chat:{settings.PROJECT_NAME}"
            )
            self._setup_analyzer()

    def _setup_analyzer(self):
        """Setup the conversation analysis chain"""
        if not self.llm:
            return

        # Create analysis prompt
        analysis_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""You are an expert policy research assistant with two main states:

1. REFINE STATE: Help users clarify their policy research question by understanding:
   - Desired outcomes (what they want to achieve)
   - Scope (demographics, geography, constraints, what to include/exclude)

2. CHAT STATE: Normal conversation after research parameters are defined

Your task is to analyze the conversation and determine:
- What state you're currently in
- Whether the user has defined their outcomes and scope clearly enough
- What search query best captures their research question so far
- Whether you have enough information to search for evidence
- What follow-up question to ask if more refinement is needed

Respond with this JSON format:
{
    "current_state": "refine" or "chat",
    "outcomes_defined": true/false,
    "scope_defined": true/false, 
    "search_query": "descriptive paragraph of the research question",
    "ready_to_search": true/false,
    "next_question": "follow-up question if needed or null",
    "reasoning": "brief explanation"
}"""
                ),
                MessagesPlaceholder(variable_name="messages"),
                HumanMessage(
                    content="Analyze this conversation and provide your assessment as JSON."
                ),
            ]
        )

        # Create the analysis chain
        json_parser = JsonOutputParser(pydantic_object=ConversationAnalysis)
        self.analyzer = analysis_prompt | self.llm | json_parser

    async def analyze_conversation(self, messages: List[Dict]) -> ConversationAnalysis:
        """Analyze conversation using AI self-assessment"""

        try:
            if self.analyzer and not settings.MOCK_OPENAI:
                # Convert to LangChain messages
                langchain_messages = []
                for msg in messages:
                    if msg.get("role") == "user":
                        langchain_messages.append(
                            HumanMessage(content=msg.get("content", ""))
                        )
                    elif msg.get("role") == "assistant":
                        langchain_messages.append(
                            AIMessage(content=msg.get("content", ""))
                        )

                try:
                    result = await self.analyzer.ainvoke(
                        {"messages": langchain_messages},
                        config={
                            "callbacks": [self.langfuse_handler]
                            if self.langfuse_handler
                            else [],
                            "tags": ["component:chat", "component:chat.analyze"],
                            "metadata": {},
                            "run_name": "chat.analyze",
                        },
                    )

                    # Handle string response
                    if isinstance(result, str):
                        result = json.loads(result)

                    return ConversationAnalysis(**result)

                except Exception as parse_error:
                    logger.warning(f"AI analysis failed: {parse_error}, using fallback")
                    return self._fallback_analysis(messages)
            else:
                return self._fallback_analysis(messages)

        except Exception as e:
            logger.error(f"Error in conversation analysis: {e}")
            return self._fallback_analysis(messages)

    def _fallback_analysis(self, messages: List[Dict]) -> ConversationAnalysis:
        """Simple fallback analysis when AI analysis fails"""

        if not messages:
            return ConversationAnalysis(
                current_state=ConversationState.REFINE,
                outcomes_defined=False,
                scope_defined=False,
                search_query="No research question defined yet",
                ready_to_search=False,
                next_question="What policy issue would you like to research?",
                reasoning="No conversation yet, starting with refinement",
            )

        # Get recent user messages
        user_messages = [
            msg.get("content", "") for msg in messages if msg.get("role") == "user"
        ]
        combined_text = " ".join(user_messages).lower()

        # Simple analysis
        outcomes_keywords = [
            "want",
            "achieve",
            "improve",
            "reduce",
            "increase",
            "goal",
            "outcome",
        ]
        scope_keywords = [
            "demographics",
            "geographic",
            "community",
            "population",
            "region",
            "focus on",
            "include",
            "exclude",
        ]

        outcomes_defined = any(
            keyword in combined_text for keyword in outcomes_keywords
        )
        scope_defined = any(keyword in combined_text for keyword in scope_keywords)

        # Build simple search query
        search_query = (
            f"Policy research on: {' '.join(user_messages[-2:])}"
            if user_messages
            else "No query yet"
        )

        ready_to_search = outcomes_defined and scope_defined and len(user_messages) >= 2

        return ConversationAnalysis(
            current_state=ConversationState.CHAT
            if ready_to_search
            else ConversationState.REFINE,
            outcomes_defined=outcomes_defined,
            scope_defined=scope_defined,
            search_query=search_query,
            ready_to_search=ready_to_search,
            next_question=None
            if ready_to_search
            else "Can you tell me more about the specific outcomes you want to achieve?",
            reasoning="Simple keyword-based analysis",
        )

    async def generate_response(
        self, messages: List[Dict], user_message: str
    ) -> Tuple[str, ConversationAnalysis]:
        """Generate response with conversation analysis"""

        try:
            # First analyze the conversation (including new message)
            analysis_messages = messages + [{"role": "user", "content": user_message}]
            analysis = await self.analyze_conversation(analysis_messages)

            if self.llm and not settings.MOCK_OPENAI:
                return await self._generate_ai_response(
                    messages, user_message, analysis
                )
            else:
                return await self._generate_mock_response(user_message, analysis)

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            # Fallback
            analysis = self._fallback_analysis(
                messages + [{"role": "user", "content": user_message}]
            )
            return await self._generate_mock_response(user_message, analysis)

    async def _generate_ai_response(
        self, messages: List[Dict], user_message: str, analysis: ConversationAnalysis
    ) -> Tuple[str, ConversationAnalysis]:
        """Generate AI response using LangChain"""

        # Create state-specific system prompt
        if analysis.current_state == ConversationState.REFINE:
            system_prompt = """You are a Policy Research Assistant in REFINEMENT mode. Your goal is to help users clearly define their policy research question.

You need to understand:
1. **OUTCOMES**: What specific changes or improvements do they want to achieve?
2. **SCOPE**: What population, geography, or constraints should be considered?

Based on the conversation analysis, guide the user to clarify missing elements. Be conversational and helpful.

**Format your responses using markdown:**
- Use **bold** for emphasis
- Use bullet points for lists
- Use questions to guide the conversation
- Be clear and structured

If the user has defined both outcomes and scope sufficiently, suggest they can start searching for evidence."""
        else:
            system_prompt = """You are a Policy Research Assistant in CHAT mode. The user has defined their research question sufficiently. 

Continue to help them refine their thinking, answer questions, or prepare for evidence search. Be helpful and conversational.

**Format your responses using markdown:**
- Use **bold** for emphasis
- Use bullet points for lists
- Use structured formatting for clarity"""

        # Build conversation
        langchain_messages = [SystemMessage(content=system_prompt)]

        # Add recent conversation history
        recent_messages = messages[-8:] if len(messages) > 8 else messages
        for msg in recent_messages:
            if msg.get("role") == "user":
                langchain_messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                langchain_messages.append(AIMessage(content=msg.get("content", "")))

        # Add current message
        langchain_messages.append(HumanMessage(content=user_message))

        # Generate response
        response = await self.llm.ainvoke(
            langchain_messages,
            config={
                "callbacks": [self.langfuse_handler] if self.langfuse_handler else [],
                "tags": ["component:chat", "component:chat.respond"],
                "metadata": {},
                "run_name": "chat.respond",
            },
        )

        return response.content, analysis

    async def _generate_mock_response(
        self, user_message: str, analysis: ConversationAnalysis
    ) -> Tuple[str, ConversationAnalysis]:
        """Generate mock response for testing"""

        if analysis.current_state == ConversationState.REFINE:
            if not analysis.outcomes_defined:
                return (
                    "I'm here to help you develop a focused policy research question! 🎯\n\n"
                    "To get started, could you tell me what **specific outcomes** you're hoping to achieve with this policy?\n\n"
                    "For example:\n"
                    "- **Health outcomes**: Reduce disease rates, improve access to care\n"
                    "- **Economic development**: Create jobs, boost local economy\n"
                    "- **Social equity**: Reduce inequality, improve inclusion\n"
                    "- **Environmental protection**: Lower emissions, improve sustainability\n\n"
                    "What's your main goal?",
                    analysis,
                )
            elif not analysis.scope_defined:
                return (
                    "**Great!** I understand your desired outcomes. 👍\n\n"
                    "Now, let's define the **scope** of your policy research:\n\n"
                    "- **Demographics**: What age groups, populations, or communities?\n"
                    "- **Geography**: Specific regions, cities, or areas?\n"
                    "- **Context**: Any particular settings or constraints?\n"
                    "- **Exclusions**: Anything you want to exclude from consideration?\n\n"
                    "This will help focus our evidence search!",
                    analysis,
                )
            else:
                return (
                    "**Perfect!** 🎉 Based on our conversation, I now understand your research focus:\n\n"
                    f"📝 **Research Question**: {analysis.search_query[:150]}...\n\n"
                    "I have enough information to start searching for:\n"
                    "- Academic research and studies\n"
                    "- Government reports and evaluations\n"
                    "- Real-world policy examples\n\n"
                    "**Ready to begin the evidence search?**",
                    analysis,
                )
        else:
            return (
                f"Thanks for the additional context! 💭\n\n"
                f"**Your input**: _{user_message}_\n\n"
                "I'm ready to help you search for evidence when you are. Is there anything else you'd like to clarify about your research question?",
                analysis,
            )


# Global instance
simplified_conversation_manager = SimplifiedConversationManager()
