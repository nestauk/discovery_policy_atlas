from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
import json
import asyncio
import logging
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.logging import logging_service

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


@router.post("/api/agent/log-search")
async def log_search(request: LogSearchRequest):
    """
    Log a search query to Supabase
    """
    try:
        search_id = await logging_service.log_search(
            project_id=request.project_id, search_query=request.search_query
        )

        if search_id:
            return {"success": True, "search_id": search_id}
        else:
            return {"success": False, "message": "Failed to log search"}

    except Exception as e:
        logger.error(f"Error logging search: {e}")
        raise HTTPException(status_code=500, detail="Failed to log search")


@router.get("/api/agent/debug")
async def debug_agent():
    """Debug endpoint to test authentication"""
    return {
        "message": "Agent API is working!",
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
async def refine_query(request: QueryRefinementRequest):
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
async def refine_query_stream(request: QueryRefinementRequest):
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
