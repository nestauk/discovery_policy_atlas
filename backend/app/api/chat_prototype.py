"""Chat prototype API router.

Isolated prototype endpoints for the conversational chat interface.
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.services.analysis.schemas import ImplementationConstraints

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat-prototype", tags=["chat-prototype"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ExtractedParams(BaseModel):
    research_question: str = ""
    population: List[str] = Field(default_factory=list)
    inner_setting: List[str] = Field(default_factory=list)
    outcome: List[str] = Field(default_factory=list)
    geography: List[str] = Field(default_factory=list)
    time_preset: str = "LAST_10_YEARS"
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    implementation_constraints: Optional[ImplementationConstraints] = None
    screening_factors: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=lambda: ["openalex", "overton"])
    max_results: int = 25


class ConverseRequest(BaseModel):
    message: str
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    use_case: str = "landscape"  # "broad" | "landscape" | "detailed"
    extracted_params: Optional[ExtractedParams] = None
    awaiting_confirmation: bool = False
    pending_action: Optional[str] = None
    pending_context_summary: Optional[str] = None


class ConverseResponse(BaseModel):
    message: str
    chips: List[str] = Field(default_factory=list)
    ready_for_plan: bool = False
    show_filters: bool = False
    requires_confirmation: bool = False
    confirmed_action: bool = False
    extracted_params: ExtractedParams = Field(default_factory=ExtractedParams)


class InternationalComparisonRequest(BaseModel):
    title: str
    abstract: str = ""
    research_question: str
    focus_terms: List[str] = Field(default_factory=list)
    country: Optional[str] = None


class InternationalComparisonResponse(BaseModel):
    why_interesting: str
    uk_relevance: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a policy research assistant helping a user define their research question \
for an evidence search. You are warm, concise, and professional.

## Your task
Guide the user through defining their research parameters by asking ONE question \
at a time. After each user response, extract structured parameters and decide \
what to ask next.

## Use-case: {use_case}

{use_case_instructions}

## Rules
1. Ask ONE question per message. Never bundle multiple questions.
2. Keep messages short (2-3 sentences max).
3. After the user answers, acknowledge briefly and move to the next topic.
4. Generate 3-5 contextual suggestion chips for each question. Chips should be \
   specific to the accumulated context (e.g. settings for "children" differ from \
   settings for "elderly").
5. Extract all structured parameters from the conversation so far.
6. If the conversation is currently waiting for confirmation before the next \
   step, answer the user's question or concern first and do not move forward \
   unless they explicitly approve it.
7. Do not ask for information the user has already given clearly.
8. Match the amount of questioning to the use-case. Broad exploration should \
   stay light; detailed evidence reviews should gather more context before \
   moving on.

## Response format
You MUST respond with valid JSON only (no markdown, no code fences):
{{
  "message": "Your conversational response asking the next question",
  "chips": ["Suggestion 1", "Suggestion 2", "Suggestion 3"],
  "show_filters": false,
  "ready_for_plan": false,
  "requires_confirmation": false,
  "confirmed_action": false,
  "extracted_params": {{
    "research_question": "...",
    "population": [],
    "inner_setting": [],
    "outcome": [],
    "geography": [],
    "time_preset": "LAST_10_YEARS",
    "implementation_constraints": null,
    "screening_factors": [],
    "sources": ["openalex", "overton"],
    "max_results": 25
  }}
}}

Set "show_filters" to true when all conversational questions for this use-case \
are done and the user should see the filters card. Do NOT set ready_for_plan \
to true — the frontend handles that after filters are confirmed.

If awaiting_confirmation is true:
- The user is deciding whether to proceed with a pending action.
- If the user asks a question, answer it briefly using the available context, \
  then remind them they can proceed or change something. Set \
  "requires_confirmation" to true and "confirmed_action" to false.
- If the user explicitly approves proceeding (for example: "yes", "go ahead", \
  "proceed", "start"), set "confirmed_action" to true and \
  "requires_confirmation" to false. Keep the message short.
- If the user wants to change or refine the scope instead, continue the intake \
  conversation from that change. Set "requires_confirmation" to false and \
  "confirmed_action" to false.
- While awaiting confirmation, do not silently advance to the next action.

When the user sends a message summarising their filter choices (e.g. "Academic + \
grey literature, last 10 years, anywhere, 25 results per source"), set \
"ready_for_plan" to true and provide a brief confirmation message. Do not ask \
any more questions at that point.

## Current confirmation state
awaiting_confirmation: {awaiting_confirmation}
pending_action: {pending_action}
pending_context_summary: {pending_context_summary}

## Current extracted parameters
{current_params}
"""

USE_CASE_INSTRUCTIONS = {
    "broad": """\
The user wants a broad overview of a policy area. Keep it lightweight:
- Question 1: Research question (they've already typed this)
- If the topic is already specific enough to search meaningfully, set \
  show_filters to true after that.
- If the topic is very broad or underspecified (for example: "AI adoption", \
  "housing", "mental health"), ask one or two lightweight anchoring questions \
  before showing filters.
- Those clarifying questions should help anchor the search in user terms, such as:
  - which sector / system they mean
  - what angle they want to explore (overview, barriers, policy levers, risks, \
    implementation)
  - which policymaker audience or context matters most
- When the user gives an exploration angle such as risks, governance, barriers, \
  policy levers, or implementation, preserve that in extracted_params so it can \
  be reflected back later. Use outcome and/or screening_factors for this if needed.
- Only ask a second question if the first answer still leaves the topic too \
  broad to search well.
- Do NOT run a full PICO-style intake here. Do not ask separate population, \
  setting, outcome, or implementation-constraint questions unless the user \
  explicitly shifts into a deeper request.
- After those one or two clarifiers are answered, set show_filters to true.""",
    "landscape": """\
The user wants to review the landscape of potential interventions. Moderate depth:
- Question 1: Research question (they've already typed this)
- Ask for enough context to compare intervention options well, but do not \
  over-interview the user.
- Typical missing topics are:
  - population / target group affected
  - setting / context
  - desired outcomes
- If one or more of those are already clear from the user's wording, do not \
  re-ask them. Only ask for the missing pieces.
- After outcomes, set show_filters to true.
Skip implementation constraints and screening factors.""",
    "detailed": """\
The user wants detailed intervention evidence, implementation and risks. Full depth:
- Question 1: Research question (they've already typed this)
- Gather the core context needed for a more decision-ready evidence review:
  - population / target group affected
  - setting / context
  - desired outcomes
  - implementation constraints (cost tolerance, staffing capacity, complexity \
    tolerance)
  - any additional screening factors
- If the user's opening topic is too broad to support an implementation / risk \
  review, narrow it conversationally before showing filters.
- Do not re-ask anything the user has already made clear.
- After screening factors, set show_filters to true.
""",
}


def _build_system_prompt(
    use_case: str,
    params: ExtractedParams,
    awaiting_confirmation: bool = False,
    pending_action: Optional[str] = None,
    pending_context_summary: Optional[str] = None,
) -> str:
    instructions = USE_CASE_INSTRUCTIONS.get(
        use_case, USE_CASE_INSTRUCTIONS["landscape"]
    )
    return SYSTEM_PROMPT.format(
        use_case=use_case,
        use_case_instructions=instructions,
        awaiting_confirmation=str(awaiting_confirmation).lower(),
        pending_action=pending_action or "none",
        pending_context_summary=pending_context_summary or "none",
        current_params=params.model_dump_json(indent=2),
    )


INTERNATIONAL_COMPARISON_PROMPT = """\
You are helping a UK policymaker understand why one international source from an \
evidence search is worth paying attention to.

Use ONLY the title and abstract provided. Do not invent facts that are not \
supported by them. Keep the explanation concrete and concise.

Return valid JSON only:
{{
  "why_interesting": "One or two sentences explaining what is substantively interesting about this source for the user's question.",
  "uk_relevance": "One sentence explaining why it could matter for a UK policy context, phrased cautiously."
}}

Research question: {research_question}
Focus terms: {focus_terms}
Country: {country}
Title: {title}
Abstract: {abstract}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _call_llm_json(
    messages: list[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    error_context: str = "LLM call",
) -> dict:
    """Call OpenAI with JSON mode and return the parsed dict.

    Raises HTTPException on failure so callers stay concise.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = await client.chat.completions.create(
            model="gpt-5.4",
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            reasoning_effort="none",
            response_format={"type": "json_object"},
        )

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("Empty response from LLM")

        return json.loads(content)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse %s response as JSON: %s", error_context, e)
        raise HTTPException(status_code=500, detail="Failed to parse AI response")
    except Exception as e:
        logger.error("Error in %s: %s", error_context, e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to process {error_context}"
        )


def _merge_extracted_params(
    parsed_params: dict, current: ExtractedParams
) -> ExtractedParams:
    """Merge LLM-extracted params over current defaults."""
    return ExtractedParams(
        research_question=parsed_params.get(
            "research_question", current.research_question
        ),
        population=parsed_params.get("population", current.population),
        inner_setting=parsed_params.get("inner_setting", current.inner_setting),
        outcome=parsed_params.get("outcome", current.outcome),
        geography=parsed_params.get("geography", current.geography),
        time_preset=parsed_params.get("time_preset", current.time_preset),
        time_from=parsed_params.get("time_from", current.time_from),
        time_to=parsed_params.get("time_to", current.time_to),
        implementation_constraints=(
            ImplementationConstraints(**parsed_params["implementation_constraints"])
            if isinstance(parsed_params.get("implementation_constraints"), dict)
            else current.implementation_constraints
        ),
        screening_factors=parsed_params.get(
            "screening_factors", current.screening_factors
        ),
        sources=parsed_params.get("sources", current.sources),
        max_results=parsed_params.get("max_results", current.max_results),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/converse", response_model=ConverseResponse)
async def converse(
    request: ConverseRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> ConverseResponse:
    """Conversational intake endpoint for the chat prototype.

    Handles one turn of the intake conversation: takes the user's message,
    generates the next question with contextual chips, and progressively
    extracts structured search parameters.
    """
    current_params = request.extracted_params or ExtractedParams()
    system_prompt = _build_system_prompt(
        request.use_case,
        current_params,
        awaiting_confirmation=request.awaiting_confirmation,
        pending_action=request.pending_action,
        pending_context_summary=request.pending_context_summary,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        *[
            {"role": msg.role, "content": msg.content}
            for msg in request.conversation_history
        ],
        {"role": "user", "content": request.message},
    ]

    parsed = await _call_llm_json(
        messages, temperature=0.3, max_tokens=1000, error_context="converse"
    )

    params = _merge_extracted_params(parsed.get("extracted_params", {}), current_params)

    return ConverseResponse(
        message=parsed.get(
            "message", "I'm not sure what to ask next. Could you tell me more?"
        ),
        chips=parsed.get("chips", []),
        ready_for_plan=parsed.get("ready_for_plan", False),
        show_filters=parsed.get("show_filters", False),
        requires_confirmation=parsed.get("requires_confirmation", False),
        confirmed_action=parsed.get("confirmed_action", False),
        extracted_params=params,
    )


@router.post(
    "/international-comparison",
    response_model=InternationalComparisonResponse,
)
async def international_comparison(
    request: InternationalComparisonRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> InternationalComparisonResponse:
    """Generate a concise LLM judgment for why an international source is interesting."""
    prompt = INTERNATIONAL_COMPARISON_PROMPT.format(
        research_question=request.research_question,
        focus_terms=", ".join(request.focus_terms)
        if request.focus_terms
        else "none provided",
        country=request.country or "unknown",
        title=request.title,
        abstract=request.abstract or "No abstract available.",
    )

    parsed = await _call_llm_json(
        [{"role": "system", "content": prompt}],
        temperature=0.2,
        max_tokens=400,
        error_context="international comparison",
    )

    return InternationalComparisonResponse(
        why_interesting=parsed.get(
            "why_interesting",
            "This source appears relevant as an international comparator for the question.",
        ),
        uk_relevance=parsed.get(
            "uk_relevance",
            "It may offer a useful comparison point for a UK policy context.",
        ),
    )
