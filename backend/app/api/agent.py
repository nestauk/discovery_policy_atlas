from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import json
import asyncio
import logging
import uuid
from enum import Enum
from datetime import datetime
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.auth import get_current_user, CurrentUser
from app.services.logging import logging_service
from app.services.openalex import OpenAlexService
from app.services.overton import OvertonService
from app.services.screening import ScreeningService
from app.services.vectorization import vectorization_service
from app.services.rag_chat import rag_chat_service
from app.services.simplified_conversation_manager import simplified_conversation_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRefinementRequest(BaseModel):
    query: str
    max_suggestions: int = 3


class QueryRefinementSuggestion(BaseModel):
    title: str
    category: str


class QueryRefinementResponse(BaseModel):
    original_query: str
    suggestions: List[QueryRefinementSuggestion]


class LogSearchRequest(BaseModel):
    project_id: str = "test-project"  # Placeholder for now
    search_query: str


# Chat conversation models
class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    state: str
    search_query: str
    evidence_search_ready: bool = False
    outcomes_defined: bool = False
    scope_defined: bool = False


class ConversationRecord(BaseModel):
    conversation_id: str
    state: str = "refine"
    search_query: str = ""
    messages: List[ChatMessage]
    evidence_search_ready: bool = False
    outcomes_defined: bool = False
    scope_defined: bool = False
    created_at: datetime
    updated_at: datetime


# In-memory storage for conversations (should be replaced with proper DB in production)
conversation_store: Dict[str, ConversationRecord] = {}


@router.post("/api/agent/log-search")
async def log_search(
    request: LogSearchRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """
    Log a search query to Supabase
    """
    try:
        search_id = await logging_service.log_search(
            project_id=request.project_id,
            search_query=request.search_query,
            user_id=current_user.user_id,
        )

        if search_id:
            return {"success": True, "search_id": search_id}
        else:
            return {"success": False, "message": "Failed to log search"}

    except Exception as e:
        logger.error(f"Error logging search: {e}")
        raise HTTPException(status_code=500, detail="Failed to log search")


@router.get("/api/agent/debug")
async def debug_agent(current_user: CurrentUser = Depends(get_current_user)):
    """Debug endpoint to test authentication"""
    return {
        "message": "Agent API is working!",
        "user_id": current_user.user_id,
        "email": current_user.email,
        "openai_configured": bool(settings.OPENAI_API_KEY),
    }


async def generate_refinement_suggestions(
    query: str, max_suggestions: int = 3
) -> List[QueryRefinementSuggestion]:
    """
    Use OpenAI to generate query refinement suggestions
    """
    # Mock mode for testing
    if settings.MOCK_OPENAI:
        logger.info("Using mock OpenAI responses")
        return [
            QueryRefinementSuggestion(
                title=f"Mock refinement 1 for: {query}", category="Mock Category 1"
            ),
            QueryRefinementSuggestion(
                title=f"Mock refinement 2 for: {query}", category="Mock Category 2"
            ),
            QueryRefinementSuggestion(
                title=f"Mock refinement 3 for: {query}", category="Mock Category 3"
            ),
        ]

    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    system_prompt = """You are a research assistant that helps users refine their research queries to get more targeted and relevant results.

Given a research question, suggest 3 different ways to ask the same question with more detail and specificity. Each suggestion should:
1. Focus on a different aspect or angle of the original question
2. Add more specific details, context, or constraints
3. Be more targeted for academic research
4. Include a brief description of why this refinement would be useful

Format your response as a JSON array with objects containing:
- title: The refined query (in quotes)
- description: A brief explanation of why this refinement is useful
- category: A short category name (e.g., "Public Health Policy", "Regulation and Compliance", "Evidence-Based Policy")

Example format:
[
  {
    "title": "Comparative health impacts of vaping and smoking among youth",
    "description": "Focusing on youth allows for insight into preventative policies and the implications of nicotine exposure during adolescence.",
    "category": "Public Health Policy"
  }
]"""

    user_prompt = f"Original research question: {query}\n\nPlease suggest {max_suggestions} refined versions of this query."

    try:
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
            stream=False,
        )

        content = response.choices[0].message.content
        logger.info(f"OpenAI response: {content}")

        # Try to parse the JSON response
        try:
            suggestions_data = json.loads(content)
            suggestions = []

            for item in suggestions_data:
                if isinstance(item, dict) and all(
                    key in item for key in ["title", "description", "category"]
                ):
                    suggestions.append(
                        QueryRefinementSuggestion(
                            title=item["title"],
                            description=item["description"],
                            category=item["category"],
                        )
                    )

            if len(suggestions) == 0:
                raise ValueError("No valid suggestions found in response")

            return suggestions[:max_suggestions]

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            logger.error(f"Raw response: {content}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response")

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate query refinements"
        )


@router.post("/api/agent/refine-query")
async def refine_query(
    request: QueryRefinementRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate refined query suggestions using AI
    """
    try:
        suggestions = await generate_refinement_suggestions(
            request.query, request.max_suggestions
        )

        return QueryRefinementResponse(
            original_query=request.query, suggestions=suggestions
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in refine_query: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/agent/refine-query/stream")
async def refine_query_stream(
    request: QueryRefinementRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Stream refined query suggestions using AI
    """
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    system_prompt = """You are a research assistant that helps users refine their research queries to get more targeted and relevant results.

Given a research question, suggest 3 different ways to ask the same question with more detail and specificity. Each suggestion should:
1. Focus on a different aspect or angle of the original question
2. Add more specific details, context, or constraints
3. Be more targeted for academic research
4. Include a brief description of why this refinement would be useful

Format your response as a JSON array with objects containing:
- title: The refined query (in quotes)
- description: A brief explanation of why this refinement is useful
- category: A short category name (e.g., "Public Health Policy", "Regulation and Compliance", "Evidence-Based Policy")

Example format:
[
  {
    "title": "Comparative health impacts of vaping and smoking among youth",
    "description": "Focusing on youth allows for insight into preventative policies and the implications of nicotine exposure during adolescence.",
    "category": "Public Health Policy"
  }
]"""

    user_prompt = f"Original research question: {request.query}\n\nPlease suggest {request.max_suggestions} refined versions of this query."

    async def generate_stream():
        try:
            # Mock mode for testing
            if settings.MOCK_OPENAI:
                logger.info("Using mock streaming responses")
                mock_suggestions = [
                    {
                        "title": f"Mock refinement 1 for: {request.query}",
                        "category": "Mock Category 1",
                    },
                    {
                        "title": f"Mock refinement 2 for: {request.query}",
                        "category": "Mock Category 2",
                    },
                    {
                        "title": f"Mock refinement 3 for: {request.query}",
                        "category": "Mock Category 3",
                    },
                ]

                # Stream mock suggestions with delay
                for i, suggestion in enumerate(mock_suggestions):
                    yield f"data: {json.dumps({'suggestion': suggestion, 'index': i})}\n\n"
                    await asyncio.sleep(0.8)  # Same delay as real version
                return

            # Use a simpler approach - get the complete response first, then stream it
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
                stream=False,
            )

            content = response.choices[0].message.content
            logger.info(f"OpenAI response: {content}")

            # Parse the JSON response
            try:
                suggestions_data = json.loads(content)
                if isinstance(suggestions_data, list):
                    # Stream each suggestion with a delay
                    for i, item in enumerate(suggestions_data):
                        if isinstance(item, dict) and all(
                            key in item for key in ["title", "category"]
                        ):
                            suggestion = {
                                "title": item["title"],
                                "category": item["category"],
                            }
                            yield f"data: {json.dumps({'suggestion': suggestion, 'index': i})}\n\n"
                            await asyncio.sleep(
                                0.8
                            )  # Longer delay to make it more visible
                else:
                    # If it's not a list, try to parse as individual objects
                    # Look for JSON objects in the content
                    import re

                    json_objects = re.findall(r"\{[^}]*\}", content)
                    for i, obj_str in enumerate(json_objects):
                        try:
                            obj = json.loads(obj_str)
                            if isinstance(obj, dict) and all(
                                key in obj for key in ["title", "category"]
                            ):
                                suggestion = {
                                    "title": obj["title"],
                                    "category": obj["category"],
                                }
                                yield f"data: {json.dumps({'suggestion': suggestion, 'index': i})}\n\n"
                                await asyncio.sleep(0.8)
                        except json.JSONDecodeError:
                            continue

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {e}")
                yield f"data: {json.dumps({'error': 'Failed to parse AI response'})}\n\n"

        except Exception as e:
            logger.error(f"Error in streaming response: {e}")
            yield f"data: {json.dumps({'error': 'Failed to generate response'})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def get_or_create_conversation(
    conversation_id: Optional[str], user_id: str
) -> ConversationRecord:
    """Get existing conversation or create new one"""
    if conversation_id and conversation_id in conversation_store:
        return conversation_store[conversation_id]

    # Create new conversation
    import uuid

    new_id = str(uuid.uuid4())
    now = datetime.utcnow()

    conversation = ConversationRecord(
        conversation_id=new_id,
        state="refine",
        search_query="",
        messages=[],
        created_at=now,
        updated_at=now,
    )

    conversation_store[new_id] = conversation
    return conversation


async def generate_policy_assistant_response(
    conversation: ConversationRecord, user_message: str
) -> tuple[str, str, str, bool, bool, bool]:
    """Generate response using simplified LangChain conversation manager or RAG"""

    try:
        # Check if we're in chat state and have evidence available
        if conversation.state == "chat":
            # Check if evidence is available
            evidence_check = await rag_chat_service.check_evidence_availability(
                "test_project"
            )

            if evidence_check["has_evidence"]:
                # Use RAG for response
                message_dicts = []
                for msg in conversation.messages[:-1]:  # Exclude current message
                    message_dicts.append(
                        {
                            "role": msg.role.value,
                            "content": msg.content,
                            "timestamp": msg.timestamp.isoformat()
                            if msg.timestamp
                            else None,
                        }
                    )

                rag_response = await rag_chat_service.generate_rag_response(
                    user_message, message_dicts, "test_project"
                )

                return (
                    rag_response,
                    "chat",  # Stay in chat state
                    conversation.search_query,  # Keep existing search query
                    True,  # Evidence is available
                    conversation.outcomes_defined,
                    conversation.scope_defined,
                )

        # Otherwise use normal conversation manager
        message_dicts = []
        for msg in conversation.messages:
            message_dicts.append(
                {
                    "role": msg.role.value,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                }
            )

        # Use simplified conversation manager
        (
            response_content,
            analysis,
        ) = await simplified_conversation_manager.generate_response(
            message_dicts, user_message
        )

        return (
            response_content,
            analysis.current_state.value,
            analysis.search_query,
            analysis.ready_to_search,
            analysis.outcomes_defined,
            analysis.scope_defined,
        )

    except Exception as e:
        logger.error(f"Error in policy assistant response generation: {e}")
        # Fallback to simple response
        return (
            "Thank you for your message. I'm here to help you develop your policy research question. Could you tell me more about what you're trying to achieve?",
            "refine",
            "Basic policy research query",
            False,
            False,
            False,
        )


@router.post("/api/agent/chat")
async def chat_with_policy_assistant(
    request: ChatRequest, current_user: CurrentUser = Depends(get_current_user)
) -> ChatResponse:
    """
    Main chat endpoint for policy research assistant
    """
    try:
        # Get or create conversation
        conversation = get_or_create_conversation(
            request.conversation_id, current_user.user_id
        )

        # Add user message to conversation
        user_message = ChatMessage(
            role=ChatRole.USER, content=request.message, timestamp=datetime.utcnow()
        )
        conversation.messages.append(user_message)

        # Generate assistant response
        (
            assistant_content,
            new_state,
            search_query,
            evidence_ready,
            outcomes_defined,
            scope_defined,
        ) = await generate_policy_assistant_response(conversation, request.message)

        # Add assistant message to conversation
        assistant_message = ChatMessage(
            role=ChatRole.ASSISTANT,
            content=assistant_content,
            timestamp=datetime.utcnow(),
        )
        conversation.messages.append(assistant_message)

        # Update conversation state
        conversation.state = new_state
        conversation.search_query = search_query
        conversation.evidence_search_ready = evidence_ready
        conversation.outcomes_defined = outcomes_defined
        conversation.scope_defined = scope_defined
        conversation.updated_at = datetime.utcnow()

        # Update in store
        conversation_store[conversation.conversation_id] = conversation

        return ChatResponse(
            message=assistant_content,
            conversation_id=conversation.conversation_id,
            state=new_state,
            search_query=search_query,
            evidence_search_ready=evidence_ready,
            outcomes_defined=outcomes_defined,
            scope_defined=scope_defined,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/agent/conversation/{conversation_id}")
async def get_conversation(
    conversation_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> ConversationRecord:
    """Get conversation history"""
    if conversation_id not in conversation_store:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation_store[conversation_id]


@router.post("/api/agent/search-evidence")
async def search_evidence(
    conversation_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """
    Search for evidence based on conversation context
    """
    if conversation_id not in conversation_store:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversation_store[conversation_id]

    if not conversation.evidence_search_ready:
        raise HTTPException(
            status_code=400,
            detail="Conversation not ready for evidence search. Please continue refining your research question.",
        )

    try:
        # Use the AI-generated search query
        search_queries = (
            [conversation.search_query]
            if conversation.search_query
            else ["policy research review"]
        )

        # Search using OpenAlex
        openalex_service = OpenAlexService()
        all_results = []

        for query in search_queries:
            try:
                results_df = await openalex_service.search(
                    query=query,
                    max_results=20,  # Limit results per query
                    min_citations=5,
                )

                # Convert to dict format
                for _, row in results_df.iterrows():
                    all_results.append(
                        {
                            "id": row["id"],
                            "title": row["title"],
                            "abstract": row["abstract"],
                            "doi": row.get("doi"),
                            "search_query": query,
                        }
                    )

            except Exception as e:
                logger.warning(f"Search failed for query '{query}': {e}")
                continue

        # Update conversation state
        conversation.state = "chat"
        conversation.updated_at = datetime.utcnow()
        conversation_store[conversation_id] = conversation

        return {
            "conversation_id": conversation_id,
            "search_queries": search_queries,
            "evidence_count": len(all_results),
            "evidence": all_results[:50],  # Limit to 50 results for now
        }

    except Exception as e:
        logger.error(f"Error searching evidence: {e}")
        raise HTTPException(status_code=500, detail="Failed to search for evidence")


@router.post("/api/agent/search")
async def search_papers(
    request: dict, current_user: CurrentUser = Depends(get_current_user)
):
    """
    Search for papers using Overton with AI screening for agent results
    """
    query = request.get("query", "")
    conversation_id = request.get("conversation_id")
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    session_id = str(uuid.uuid4())[:8]
    logger.info(f"Starting agent search for query: {query}")

    try:
        # Use Overton semantic search
        overton_service = OvertonService()
        papers_df = await overton_service.search(
            query=query, max_results=20, semantic_search=True
        )

        if papers_df.empty:
            return {
                "papers": [],
                "total_found": 0,
                "total_screened": 0,
                "total_relevant": 0,
            }

        # Format papers for screening
        screening_texts = overton_service.format_for_screening(papers_df)

        # Perform AI screening
        screening_message = f"Determine if this document is relevant to: {query}"
        screening_service = ScreeningService(
            system_message=screening_message, extra_fields=[]
        )
        screening_df = await screening_service.screen_batch(screening_texts, session_id)

        # Merge papers with screening results
        relevant_df = (
            papers_df.merge(screening_df, left_on="id", right_on="id", how="left")
            .assign(
                is_relevant=lambda x: x["is_relevant"].fillna(False),
                relevance_reason=lambda x: x["relevance_reason"].fillna("Not screened"),
                confidence=lambda x: x["confidence"].fillna(0.0),
                top_line=lambda x: x["top_line"].fillna(""),
            )
            .query("is_relevant == True")
            .sort_values("confidence", ascending=False)
        )

        # Convert to list for response
        papers_list = relevant_df.to_dict("records")

        # Store results in Supabase with vectorization (background task)
        if papers_list:
            try:
                vectorization_result = await vectorization_service.store_search_results(
                    papers_list, project_id="test_project"
                )
                logger.info(f"Vectorization result: {vectorization_result}")
            except Exception as e:
                logger.error(f"Error during vectorization: {e}")
                # Don't fail the request if vectorization fails

        logger.info(
            f"Search completed: {len(papers_df)} found, {len(relevant_df)} relevant"
        )

        # Update conversation state to "chat" if conversation_id is provided and results found
        if (
            conversation_id
            and conversation_id in conversation_store
            and len(relevant_df) > 0
        ):
            conversation = conversation_store[conversation_id]
            conversation.state = "chat"
            conversation.updated_at = datetime.utcnow()
            conversation_store[conversation_id] = conversation
            logger.info(f"Updated conversation {conversation_id} to chat state")

        return {
            "papers": papers_list,
            "total_found": len(papers_df),
            "total_screened": len(screening_df),
            "total_relevant": len(relevant_df),
            "conversation_updated": conversation_id is not None
            and len(relevant_df) > 0,
        }

    except Exception as e:
        logger.error(f"Error in agent search: {e}")
        raise HTTPException(status_code=500, detail="Failed to search for papers")
