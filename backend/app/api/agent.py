from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import json
import asyncio
import logging
import uuid
import pandas as pd
import math
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
from app.services.advanced_rag import advanced_rag_service

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
    project_id: Optional[str] = None


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


async def generate_insights_background(query: str, project_id: str, session_id: str):
    """Background task to generate insights after search completion"""
    try:
        logger.info(
            f"Background insights generation started for project {project_id} | session: {session_id}"
        )

        # Extract insights using the advanced RAG service
        insights = await advanced_rag_service.extract_key_insights(
            user_query=query, project_id=project_id
        )

        # Review the insights
        review = await advanced_rag_service.review_insights(insights)

        # If not approved and quality is low, try once more with enhanced query
        if not review.approved and review.score < 0.6:
            logger.info(
                f"Insights quality below threshold ({review.score:.2f}), retrying with enhanced query..."
            )
            enhanced_query = f"{query} - provide detailed analysis with specific evidence and data points"
            insights = await advanced_rag_service.extract_key_insights(
                user_query=enhanced_query, project_id=project_id
            )
            review = await advanced_rag_service.review_insights(insights)

        # Save insights to project (always save, even if not fully approved)
        insights_data = {
            "extraction": insights.model_dump(),
            "review": review.model_dump(),
            "query": query,
            "extracted_at": datetime.utcnow().isoformat(),
            "quality_score": review.score,
            "auto_generated": True,  # Mark as automatically generated
            "session_id": session_id,
        }

        # Update project with insights
        result = (
            vectorization_service.supabase.table("projects")
            .update(
                {
                    "key_insights": insights_data,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", project_id)
            .execute()
        )

        if result.data:
            logger.info(
                f"✅ Background insights saved to project {project_id} | "
                f"Quality: {review.score * 100:.0f}% | "
                f"Approved: {review.approved} | "
                f"Insights: {len(insights.insights)}"
            )

            # If insights are approved, trigger policy recommendations generation
            if review.approved and len(insights.insights) >= 2:
                try:
                    logger.info(
                        f"Starting policy recommendations generation for project {project_id}"
                    )
                    asyncio.create_task(
                        generate_policy_recommendations_background(
                            query, project_id, session_id, insights
                        )
                    )
                    logger.info(
                        f"Initiated background policy recommendations for project {project_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to initiate policy recommendations: {e}")
        else:
            logger.error(
                f"❌ Failed to save background insights to project {project_id}"
            )

    except Exception as e:
        logger.error(
            f"❌ Error in background insights generation for project {project_id}: {e}"
        )
        import traceback

        traceback.print_exc()


async def generate_policy_recommendations_background(
    query: str, project_id: str, session_id: str, insights: any
):
    """Background task to generate policy recommendations after insights completion"""
    try:
        logger.info(
            f"Background policy recommendations started for project {project_id} | session: {session_id}"
        )

        # Generate policy recommendations
        recommendations = await advanced_rag_service.generate_policy_recommendations(
            user_query=query, insights=insights, project_id=project_id
        )

        # Review the recommendations
        review = await advanced_rag_service.review_recommendations(recommendations)

        # If not approved and quality is low, try once more
        if not review.approved and review.score < 0.6:
            logger.info(
                f"Recommendations quality below threshold ({review.score:.2f}), retrying..."
            )
            enhanced_query = f"{query} - provide specific, actionable policy recommendations with implementation guidance"
            recommendations = (
                await advanced_rag_service.generate_policy_recommendations(
                    user_query=enhanced_query, insights=insights, project_id=project_id
                )
            )
            review = await advanced_rag_service.review_recommendations(recommendations)

        # Save recommendations to project
        recommendations_data = {
            "recommendations": recommendations.model_dump(),
            "review": review.model_dump(),
            "query": query,
            "generated_at": datetime.utcnow().isoformat(),
            "quality_score": review.score,
            "auto_generated": True,
            "session_id": session_id,
        }

        # Update project with recommendations
        result = (
            vectorization_service.supabase.table("projects")
            .update(
                {
                    "policy_recommendations": recommendations_data,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", project_id)
            .execute()
        )

        if result.data:
            logger.info(
                f"✅ Background recommendations saved to project {project_id} | "
                f"Quality: {review.score * 100:.0f}% | "
                f"Approved: {review.approved} | "
                f"Recommendations: {len(recommendations.recommendations)}"
            )

            # If recommendations are approved, trigger executive brief generation
            if review.approved and len(recommendations.recommendations) >= 1:
                try:
                    logger.info(
                        f"Starting executive brief generation for project {project_id}"
                    )
                    asyncio.create_task(
                        generate_executive_brief_background(
                            query, project_id, session_id, insights, recommendations
                        )
                    )
                    logger.info(
                        f"Initiated background executive brief for project {project_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to initiate executive brief: {e}")
        else:
            logger.error(
                f"❌ Failed to save background recommendations to project {project_id}"
            )

    except Exception as e:
        logger.error(
            f"❌ Error in background recommendations generation for project {project_id}: {e}"
        )
        import traceback

        traceback.print_exc()


async def generate_executive_brief_background(
    query: str, project_id: str, session_id: str, insights: any, recommendations: any
):
    """Background task to generate executive brief after recommendations completion"""
    try:
        logger.info(
            f"Background executive brief started for project {project_id} | session: {session_id}"
        )

        # Generate executive brief
        brief = await advanced_rag_service.generate_executive_brief(
            user_query=query,
            insights=insights,
            recommendations=recommendations,
            project_id=project_id,
        )

        # Save brief to project
        brief_data = {
            "brief": brief.model_dump(),
            "query": query,
            "generated_at": datetime.utcnow().isoformat(),
            "auto_generated": True,
            "session_id": session_id,
        }

        # Update project with executive brief
        result = (
            vectorization_service.supabase.table("projects")
            .update(
                {
                    "executive_brief": brief_data,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", project_id)
            .execute()
        )

        if result.data:
            logger.info(f"✅ Background executive brief saved to project {project_id}")
        else:
            logger.error(
                f"❌ Failed to save background executive brief to project {project_id}"
            )

    except Exception as e:
        logger.error(
            f"❌ Error in background executive brief generation for project {project_id}: {e}"
        )
        import traceback

        traceback.print_exc()


async def generate_policy_assistant_response(
    conversation: ConversationRecord,
    user_message: str,
    project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
) -> tuple[str, str, str, bool, bool, bool]:
    """Generate response using simplified LangChain conversation manager or RAG"""

    try:
        # Check if we're in chat state and have evidence available
        if conversation.state == "chat":
            # Check if evidence is available
            evidence_check = await rag_chat_service.check_evidence_availability(
                project_id
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
                    user_message, message_dicts, project_id
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
        ) = await generate_policy_assistant_response(
            conversation,
            request.message,
            request.project_id or "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        )

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
    project_id = request.get(
        "project_id", "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    )  # Default to test project UUID for backward compatibility
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    session_id = str(uuid.uuid4())[:8]
    logger.info(
        f"Starting agent search for query: {query} | session: {session_id} | project: {project_id} | conversation: {conversation_id}"
    )

    try:
        # Run both Overton and OpenAlex searches in parallel
        overton_service = OvertonService()
        openalex_service = OpenAlexService()

        # Execute searches concurrently
        overton_task = overton_service.search(
            query=query, max_results=20, semantic_search=True
        )
        openalex_task = openalex_service.search_for_agent(
            query=query, max_results=20, focus_on_reviews=True
        )

        overton_df, openalex_df = await asyncio.gather(
            overton_task, openalex_task, return_exceptions=True
        )

        # Handle any exceptions from the searches
        if isinstance(overton_df, Exception):
            logger.error(f"Overton search failed: {overton_df}")
            overton_df = pd.DataFrame()

        if isinstance(openalex_df, Exception):
            logger.error(f"OpenAlex search failed: {openalex_df}")
            openalex_df = pd.DataFrame()

        # Combine results from both sources
        all_papers = []
        papers_df = pd.DataFrame()

        # Add Overton results
        if not overton_df.empty:
            overton_papers = overton_df.copy()
            overton_papers["source"] = "overton"
            all_papers.append(overton_papers)
            logger.info(f"Overton returned {len(overton_papers)} papers")

        # Add OpenAlex results
        if not openalex_df.empty:
            openalex_papers = openalex_df.copy()
            openalex_papers["source"] = "openalex"
            all_papers.append(openalex_papers)
            logger.info(f"OpenAlex returned {len(openalex_papers)} papers")

        # Combine all results if we have any
        if all_papers:
            papers_df = pd.concat(all_papers, ignore_index=True)
            # Remove duplicates based on title similarity (basic deduplication)
            papers_df = papers_df.drop_duplicates(subset=["title"], keep="first")
            logger.info(f"Combined search returned {len(papers_df)} unique papers")

        if papers_df.empty:
            return {
                "papers": [],
                "total_found": 0,
                "total_screened": 0,
                "total_relevant": 0,
                "sources_used": ["overton", "openalex"],
                "overton_count": 0,
                "openalex_count": 0,
            }

        # Format papers for screening - ensure we have the required columns
        # Both services should provide 'id', 'title', and 'content' columns
        if "content" not in papers_df.columns and "abstract" in papers_df.columns:
            papers_df["content"] = papers_df["abstract"].str[:1000]

        screening_texts = overton_service.format_for_screening(papers_df)

        # Perform AI screening
        screening_message = f"Determine if this document is relevant to: {query}"
        screening_service = ScreeningService(
            system_message=screening_message, extra_fields=[]
        )
        screening_df = await screening_service.screen_batch(screening_texts, session_id)

        # Merge papers with screening results
        merged_df = papers_df.merge(
            screening_df, left_on="id", right_on="id", how="left"
        )

        # Clean NaN values before filtering
        merged_df["is_relevant"] = merged_df["is_relevant"].fillna(False)
        merged_df["relevance_reason"] = merged_df["relevance_reason"].fillna(
            "Not screened"
        )
        merged_df["confidence"] = merged_df["confidence"].fillna(0.0)
        merged_df["top_line"] = merged_df["top_line"].fillna("")
        # Default new list fields to []
        if "key_facts" not in merged_df.columns:
            merged_df["key_facts"] = [[] for _ in range(len(merged_df))]
        else:
            merged_df["key_facts"] = merged_df["key_facts"].apply(
                lambda v: v
                if isinstance(v, list)
                else ([] if pd.isna(v) else ([v] if v not in ("", None) else []))
            )
        if "policy_recommendations" not in merged_df.columns:
            merged_df["policy_recommendations"] = [[] for _ in range(len(merged_df))]
        else:
            merged_df["policy_recommendations"] = merged_df[
                "policy_recommendations"
            ].apply(
                lambda v: v
                if isinstance(v, list)
                else ([] if pd.isna(v) else ([v] if v not in ("", None) else []))
            )

        # Filter for relevant papers using boolean indexing instead of query
        relevant_df = merged_df[merged_df["is_relevant"]].copy()
        relevant_df = relevant_df.sort_values("confidence", ascending=False)

        # Convert to list for response and clean NaN values
        papers_list = relevant_df.to_dict("records")

        # Clean any NaN values that might cause JSON serialization issues
        for paper in papers_list:
            for key, value in paper.items():
                # Check for NaN values safely
                is_nan = False
                try:
                    if isinstance(value, float) and math.isnan(value):
                        is_nan = True
                    elif value is None:
                        is_nan = True
                except (TypeError, ValueError):
                    # Not a number type, skip
                    pass

                if is_nan:
                    if key in ["confidence"]:
                        paper[key] = 0.0
                    elif key in ["is_relevant"]:
                        paper[key] = False
                    elif key in ["cited_by_count", "publication_year"]:
                        paper[key] = 0
                    elif key in ["key_facts", "policy_recommendations"]:
                        paper[key] = []
                    else:
                        # Default to empty string for scalar text fields
                        paper[key] = ""

        # Store results in Supabase with vectorization (background task)
        project_stats_updated = False
        if papers_list:
            try:
                vectorization_result = await vectorization_service.store_search_results(
                    papers_list, project_id=project_id
                )
                logger.info(f"Vectorization result: {vectorization_result}")

                # Update project stats after storing results
                try:
                    # Count all documents for this project to set total evidence_count
                    count_result = (
                        vectorization_service.supabase.table("documents")
                        .select("id", count="exact")
                        .eq("project_id", project_id)
                        .execute()
                    )
                    total_evidence_count = (
                        count_result.count
                        if hasattr(count_result, "count")
                        else len(count_result.data or [])
                    )

                    update_data = {
                        "evidence_count": total_evidence_count,
                        "last_search_date": datetime.utcnow().isoformat(),
                        "last_search_query": query,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                    (
                        vectorization_service.supabase.table("projects")
                        .update(update_data)
                        .eq("id", project_id)
                        .execute()
                    )
                    logger.info(
                        f"Updated project {project_id} stats (evidence_count={total_evidence_count})"
                    )
                    project_stats_updated = True
                except Exception as e:
                    logger.warning(f"Failed to update project stats: {e}")

                # Automatically generate insights after successful vectorization
                if (
                    len(papers_list) >= 3
                ):  # Only generate insights if we have sufficient evidence
                    try:
                        logger.info(
                            f"Starting automatic insights generation for project {project_id}"
                        )

                        # Use the search query as the insights query
                        insights_query = f"What are the key findings and insights from the evidence about: {query}"

                        # Generate insights in the background (don't block the search response)
                        asyncio.create_task(
                            generate_insights_background(
                                insights_query, project_id, session_id
                            )
                        )

                        logger.info(
                            f"Initiated background insights generation for project {project_id}"
                        )

                    except Exception as e:
                        logger.warning(f"Failed to initiate insights generation: {e}")
                        # Don't fail the search if insights generation fails to start

            except Exception as e:
                logger.error(f"Error during vectorization: {e}")
                # Don't fail the request if vectorization fails

        # Ensure project stats are up-to-date even if no papers were stored
        if not project_stats_updated:
            try:
                count_result = (
                    vectorization_service.supabase.table("documents")
                    .select("id", count="exact")
                    .eq("project_id", project_id)
                    .execute()
                )
                total_evidence_count = (
                    count_result.count
                    if hasattr(count_result, "count")
                    else len(count_result.data or [])
                )
                update_data = {
                    "evidence_count": total_evidence_count,
                    "last_search_date": datetime.utcnow().isoformat(),
                    "last_search_query": query,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                (
                    vectorization_service.supabase.table("projects")
                    .update(update_data)
                    .eq("id", project_id)
                    .execute()
                )
                logger.info(
                    f"Ensured project {project_id} stats updated (evidence_count={total_evidence_count})"
                )
            except Exception as e:
                logger.warning(f"Failed to ensure project stats update: {e}")

        # Calculate source-specific counts
        overton_count = len(overton_df) if not overton_df.empty else 0
        openalex_count = len(openalex_df) if not openalex_df.empty else 0

        logger.info(
            f"Search completed: {len(papers_df)} found ({overton_count} from Overton, {openalex_count} from OpenAlex), {len(relevant_df)} relevant"
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
            "sources_used": ["overton", "openalex"],
            "overton_count": overton_count,
            "openalex_count": openalex_count,
            "conversation_updated": conversation_id is not None
            and len(relevant_df) > 0,
        }

    except Exception as e:
        logger.error(f"Error in agent search: {e}")
        raise HTTPException(status_code=500, detail="Failed to search for papers")


class AdvancedRAGRequest(BaseModel):
    query: str
    project_id: Optional[str] = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


@router.post("/api/agent/extract-insights")
async def extract_key_insights(
    request: AdvancedRAGRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Extract key insights from evidence using advanced RAG"""
    try:
        # Extract insights
        insights = await advanced_rag_service.extract_key_insights(
            user_query=request.query, project_id=request.project_id
        )

        # Review the insights
        review = await advanced_rag_service.review_insights(insights)

        # If not approved and we haven't retried, try once more
        if not review.approved and review.score < 0.6:
            logger.info("Insights quality below threshold, retrying extraction...")
            insights = await advanced_rag_service.extract_key_insights(
                user_query=f"{request.query} - provide more detailed analysis",
                project_id=request.project_id,
            )
            review = await advanced_rag_service.review_insights(insights)

        # Save insights to project if approved
        if review.approved:
            try:
                insights_data = {
                    "extraction": insights.model_dump(),
                    "review": review.model_dump(),
                    "query": request.query,
                    "extracted_at": datetime.utcnow().isoformat(),
                    "quality_score": review.score,
                }

                # Update project with insights
                vectorization_service.supabase.table("projects").update(
                    {
                        "key_insights": insights_data,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", request.project_id).execute()

                logger.info(f"Saved insights to project {request.project_id}")

            except Exception as save_error:
                logger.error(f"Error saving insights to project: {save_error}")
                # Don't fail the request if saving fails

        return {
            "insights": insights.model_dump(),
            "review": review.model_dump(),
            "quality_score": review.score,
            "approved": review.approved,
            "saved_to_project": review.approved,
        }

    except Exception as e:
        logger.error(f"Error extracting insights: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to extract insights: {str(e)}"
        )


@router.get("/api/agent/evidence-status/{project_id}")
async def check_evidence_status(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Check if evidence is available for advanced RAG analysis"""
    try:
        evidence_check = await rag_chat_service.check_evidence_availability(project_id)

        # Get additional details for advanced RAG
        documents = vectorization_service.get_project_documents(project_id)

        document_summaries = []
        for doc in documents[:10]:  # Show first 10
            document_summaries.append(
                {
                    "title": doc.get("title", ""),
                    "confidence": doc.get("confidence", 0.0),
                    "source_country": doc.get("source_country", ""),
                    "top_line": doc.get("top_line", ""),
                }
            )

        return {
            "has_evidence": evidence_check["has_evidence"],
            "document_count": evidence_check["document_count"],
            "ready_for_advanced_rag": evidence_check["document_count"] >= 3,
            "document_summaries": document_summaries,
            "recommendation": (
                "Ready for advanced analysis"
                if evidence_check["document_count"] >= 3
                else "Need more evidence for comprehensive analysis"
            ),
        }

    except Exception as e:
        logger.error(f"Error checking evidence status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check evidence status")


class RestartAnalysisRequest(BaseModel):
    project_id: str
    query: Optional[str] = None


@router.post("/api/agent/restart-analysis")
async def restart_analysis(
    request: RestartAnalysisRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Manually restart insights → recommendations → executive brief generation"""
    try:
        project_id = request.project_id
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required")

        # Build insights query
        # Prefer the project's last_search_query if available
        try:
            proj = (
                vectorization_service.supabase.table("projects")
                .select("last_search_query")
                .eq("id", project_id)
                .single()
                .execute()
            )
            saved_query = (
                (proj.data or {}).get("last_search_query")
                if hasattr(proj, "data")
                else None
            )
        except Exception:
            saved_query = None

        base_query = (
            request.query or saved_query or f"Policy analysis for project {project_id}"
        )
        insights_query = f"What are the key findings and insights from the evidence about: {base_query}"

        session_id = str(uuid.uuid4())[:8]
        logger.info(
            f"Manual restart of analysis for project {project_id} | session: {session_id}"
        )

        # Kick off background insights generation; downstream steps are chained
        asyncio.create_task(
            generate_insights_background(insights_query, project_id, session_id)
        )

        return {"started": True, "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to restart analysis")
