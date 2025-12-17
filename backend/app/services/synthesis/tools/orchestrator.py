"""
Orchestrator for tool-augmented briefing generation.

Manages the interaction loop between the orchestrator LLM (gpt-5.2),
tool execution, section generation (gpt-5-mini), and verification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.services.synthesis.tools.base import (
    get_tool_registry,
)
from app.services.synthesis.tools.models import (
    ORCHESTRATOR_MODEL,
    ORCHESTRATOR_TEMPERATURE,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# Maximum tool calls per section (user-configured)
MAX_TOOL_CALLS_PER_SECTION = 5


ORCHESTRATOR_SYSTEM_PROMPT = """You are an evidence orchestrator for policy briefings. Your role is to:

1. Decide which tools to call to gather relevant evidence for a section
2. Analyse tool results to determine if you have sufficient evidence
3. Stop gathering when you have enough high-quality, relevant evidence

## Available Tools
{tool_descriptions}

## Guidelines

### Evidence Quality
- Prioritise evidence with high relevance scores (6+) and document quality (4+ stars)
- Prefer RCS-scored evidence (from get_theme_evidence) over raw search results
- Each claim should be supported by at least one citation

### Tool Selection Strategy
1. Start with get_theme_evidence for the main topic/intervention
2. Use search_extractions for specific claims that need additional support
3. Use get_document_quality to verify source quality for key citations
4. Stop when you have 3-5 high-quality evidence items per major claim

### Efficiency
- You have a maximum of {max_tool_calls} tool calls per section
- Combine related queries where possible
- Don't repeat the same tool call

## Response Format

When deciding on tool calls, respond with a JSON object:
{{
    "reasoning": "Brief explanation of why you're calling these tools",
    "tool_calls": [
        {{
            "tool": "tool_name",
            "arguments": {{...}}
        }}
    ],
    "done": false
}}

When you have enough evidence, respond with:
{{
    "reasoning": "Explanation of why evidence is sufficient",
    "tool_calls": [],
    "done": true,
    "evidence_summary": "Brief summary of the evidence gathered"
}}

Only output JSON, no other text."""


SECTION_GENERATION_PROMPT = """You are writing a section of a policy executive briefing.

## Section: {section_name}
{section_instructions}

## Available Evidence
{evidence_context}

## Citation Rules
- ONLY cite sources from the evidence above using [N] format
- DO NOT invent citation numbers
- Every major claim must have at least one citation
- Use multiple citations [1], [3] when evidence from multiple sources supports a claim

## Output Format
Write the section content in markdown. Include citations inline.

{additional_instructions}"""


VERIFICATION_PROMPT = """You are verifying a section of a policy briefing for grounded citations.

## Section Content
{section_content}

## Available Evidence
{evidence_context}

## Task
1. Extract each major claim from the section
2. Check if each claim is supported by the cited evidence
3. Identify any unsupported claims or incorrect citations

Respond with JSON:
{{
    "claims": [
        {{
            "claim": "claim text",
            "citations": [1, 3],
            "is_supported": true/false,
            "issue": "description if not supported, null otherwise"
        }}
    ],
    "overall_supported": true/false,
    "issues_summary": "summary of issues if any, null otherwise",
    "suggested_fixes": ["fix 1", "fix 2"] or []
}}

Only output JSON."""


@dataclass
class OrchestratorContext:
    """Context for orchestrator execution.

    Attributes:
        state: Synthesis state dictionary.
        section_name: Name of the section being generated.
        section_instructions: Specific instructions for the section.
        gathered_evidence: Evidence gathered from tool calls.
        tool_call_count: Number of tool calls made.
        max_tool_calls: Maximum allowed tool calls.
    """

    state: Dict[str, Any]
    section_name: str
    section_instructions: str
    gathered_evidence: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_count: int = 0
    max_tool_calls: int = MAX_TOOL_CALLS_PER_SECTION


class SectionOutput(BaseModel):
    """Output from section generation.

    Attributes:
        content: Generated section content in markdown.
        citations_used: List of [N] citations referenced.
        verification_passed: Whether verification was successful.
        verification_issues: List of issues found during verification.
        tool_calls_made: Number of tool calls made to gather evidence.
    """

    content: str
    citations_used: List[int] = Field(default_factory=list)
    verification_passed: bool = True
    verification_issues: List[str] = Field(default_factory=list)
    tool_calls_made: int = 0


class BriefingOrchestrator:
    """Orchestrates tool-augmented briefing section generation.

    Uses a multi-phase approach:
    1. Evidence gathering (orchestrator decides which tools to call)
    2. Section generation (using gathered evidence)
    3. Verification (checking claims against evidence)
    4. Iteration if verification fails (up to 2 retries)
    """

    def __init__(self, state: Dict[str, Any]):
        """Initialise the orchestrator.

        Args:
            state: Synthesis state with pre-computed RCS and citations.
        """
        self.state = state
        self.registry = get_tool_registry()

        # Initialise LLMs
        self.orchestrator_llm = ChatOpenAI(
            model=ORCHESTRATOR_MODEL,
            temperature=ORCHESTRATOR_TEMPERATURE,
        )
        self.generation_llm = ChatOpenAI(
            model=GENERATION_MODEL,
            temperature=GENERATION_TEMPERATURE,
        )

    async def generate_section(
        self,
        section_name: str,
        section_instructions: str,
        additional_instructions: str = "",
        max_retries: int = 2,
    ) -> SectionOutput:
        """Generate a briefing section with tool-augmented evidence.

        Args:
            section_name: Name of the section (e.g., "Background").
            section_instructions: What the section should cover.
            additional_instructions: Extra formatting/content guidance.
            max_retries: Max verification retry attempts.

        Returns:
            SectionOutput with content and verification status.
        """
        ctx = OrchestratorContext(
            state=self.state,
            section_name=section_name,
            section_instructions=section_instructions,
        )

        # Phase 1: Gather evidence
        await self._gather_evidence(ctx)

        # Phase 2 & 3: Generate and verify (with retries)
        for attempt in range(max_retries + 1):
            # Generate section
            content = await self._generate_section_content(
                ctx,
                additional_instructions,
            )

            # Extract citations used
            citations_used = self._extract_citations(content)

            # Verify
            verification = await self._verify_section(ctx, content)

            if verification["overall_supported"]:
                return SectionOutput(
                    content=content,
                    citations_used=citations_used,
                    verification_passed=True,
                    verification_issues=[],
                    tool_calls_made=ctx.tool_call_count,
                )

            # If not supported and we have retries left
            if attempt < max_retries:
                logger.warning(
                    f"Section '{section_name}' verification failed (attempt {attempt + 1}), "
                    f"issues: {verification.get('issues_summary')}"
                )
                # Add verification feedback to context for retry
                ctx.gathered_evidence.append(
                    {
                        "type": "verification_feedback",
                        "issues": verification.get("suggested_fixes", []),
                        "claims_to_fix": [
                            c
                            for c in verification.get("claims", [])
                            if not c.get("is_supported", True)
                        ],
                    }
                )

        # Exhausted retries
        return SectionOutput(
            content=content,
            citations_used=citations_used,
            verification_passed=False,
            verification_issues=verification.get("suggested_fixes", []),
            tool_calls_made=ctx.tool_call_count,
        )

    async def _gather_evidence(self, ctx: OrchestratorContext) -> None:
        """Use orchestrator LLM to decide which tools to call.

        Args:
            ctx: Orchestrator context to update with evidence.
        """
        # Build tool descriptions
        tool_descriptions = self._build_tool_descriptions()

        # Build system prompt
        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
            tool_descriptions=tool_descriptions,
            max_tool_calls=ctx.max_tool_calls,
        )

        # Initial user message
        user_message = f"""## Section: {ctx.section_name}
{ctx.section_instructions}

## Pre-computed Evidence Available
- {len(self.state.get("scored_theme_evidence", []))} theme evidence sets
- {len(self.state.get("scored_issue_evidence", []))} issue evidence sets
- {len(self.state.get("grounded_citations", []))} grounded citations
- {len(self.state.get("all_scored_contexts", []))} total scored contexts

Decide which tools to call to gather the most relevant evidence for this section."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Orchestrator loop
        while ctx.tool_call_count < ctx.max_tool_calls:
            # Get LLM decision
            config = self._build_langfuse_config("orchestrator_decide")
            response = await self.orchestrator_llm.ainvoke(messages, config=config)

            # Parse response
            try:
                content = response.content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                decision = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to parse orchestrator response: {response.content}"
                )
                break

            # Check if done
            if decision.get("done", False):
                logger.info(
                    f"Orchestrator done gathering evidence: {decision.get('reasoning', '')}"
                )
                break

            # Execute tool calls
            tool_calls = decision.get("tool_calls", [])
            if not tool_calls:
                break

            tool_results: List[Dict[str, Any]] = []
            for tc in tool_calls:
                if ctx.tool_call_count >= ctx.max_tool_calls:
                    break

                tool_name = tc.get("tool", "")
                arguments = tc.get("arguments", {})

                result = await self.registry.execute(
                    tool_name,
                    ctx.state,
                    **arguments,
                )
                ctx.tool_call_count += 1

                tool_result = {
                    "tool": tool_name,
                    "arguments": arguments,
                    "success": result.success,
                    "data": result.data if result.success else None,
                    "error": result.error if not result.success else None,
                    "fallback_used": result.fallback_used,
                }
                tool_results.append(tool_result)

                if result.success and result.data:
                    ctx.gathered_evidence.append(
                        {
                            "tool": tool_name,
                            "data": result.data,
                        }
                    )

            # Add tool results to conversation
            results_summary = json.dumps(tool_results, indent=2, default=str)
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool results:\n```json\n{results_summary}\n```\n\nDecide next action.",
                }
            )

        logger.info(
            f"Evidence gathering complete: {ctx.tool_call_count} tool calls, "
            f"{len(ctx.gathered_evidence)} evidence items"
        )

    async def _generate_section_content(
        self,
        ctx: OrchestratorContext,
        additional_instructions: str,
    ) -> str:
        """Generate section content using gathered evidence.

        Args:
            ctx: Context with gathered evidence.
            additional_instructions: Extra instructions for the section.

        Returns:
            Generated section content in markdown.
        """
        # Build evidence context
        evidence_context = self._format_evidence_for_generation(ctx)

        prompt = SECTION_GENERATION_PROMPT.format(
            section_name=ctx.section_name,
            section_instructions=ctx.section_instructions,
            evidence_context=evidence_context,
            additional_instructions=additional_instructions,
        )

        config = self._build_langfuse_config("generate_section")
        response = await self.generation_llm.ainvoke(prompt, config=config)

        return response.content.strip()

    async def _verify_section(
        self,
        ctx: OrchestratorContext,
        content: str,
    ) -> Dict[str, Any]:
        """Verify section content against evidence.

        Args:
            ctx: Context with gathered evidence.
            content: Generated section content.

        Returns:
            Verification result dictionary.
        """
        evidence_context = self._format_evidence_for_generation(ctx)

        prompt = VERIFICATION_PROMPT.format(
            section_content=content,
            evidence_context=evidence_context,
        )

        # Use generation LLM for verification (it's gpt-5-mini)
        config = self._build_langfuse_config("verify_section")
        response = await self.generation_llm.ainvoke(prompt, config=config)

        try:
            content_text = response.content.strip()
            if content_text.startswith("```"):
                content_text = content_text.split("```")[1]
                if content_text.startswith("json"):
                    content_text = content_text[4:]
            return json.loads(content_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse verification response")
            return {
                "claims": [],
                "overall_supported": False,
                "issues_summary": "Could not parse verification result",
                "suggested_fixes": [],
            }

    def _build_tool_descriptions(self) -> str:
        """Build formatted tool descriptions for the orchestrator.

        Returns:
            Formatted string of tool descriptions.
        """
        tools = self.registry.get_all()
        descriptions = []
        for tool in tools:
            schema = tool.get_schema()
            func = schema.get("function", {})
            name = func.get("name", tool.name)
            desc = func.get("description", "")
            params = func.get("parameters", {}).get("properties", {})

            param_str = ", ".join(
                f"{k}: {v.get('type', 'any')}" for k, v in params.items()
            )
            descriptions.append(f"- **{name}**({param_str}): {desc}")

        return "\n".join(descriptions)

    def _format_evidence_for_generation(self, ctx: OrchestratorContext) -> str:
        """Format gathered evidence for the generation prompt.

        Args:
            ctx: Context with gathered evidence.

        Returns:
            Formatted evidence string.
        """
        parts: List[str] = []

        for i, ev in enumerate(ctx.gathered_evidence, 1):
            tool = ev.get("tool", "unknown")
            data = ev.get("data", {})

            if tool == "verification_feedback":
                # Include verification feedback for retry
                issues = ev.get("issues", [])
                parts.append(
                    "### Verification Feedback\nFix these issues:\n"
                    + "\n".join(f"- {issue}" for issue in issues)
                )
                continue

            if isinstance(data, list):
                # List of evidence items
                items = []
                for item in data[:5]:  # Limit to 5 per tool call
                    if isinstance(item, dict):
                        cit = item.get("citation_number", "?")
                        summary = item.get("summary", item.get("content", ""))[:300]
                        title = item.get("document_title", "Unknown")
                        rel = item.get(
                            "relevance_score", item.get("similarity_score", "?")
                        )
                        items.append(
                            f"[{cit}] ({title}): {summary}... (relevance: {rel})"
                        )
                if items:
                    parts.append(f"### Evidence from {tool}\n" + "\n".join(items))
            elif isinstance(data, dict):
                # Single result (e.g., document quality)
                cit = data.get("citation_number", "?")
                title = data.get("title", "Unknown")
                ev_str = data.get("evidence_strength", "?")
                parts.append(
                    f"### {tool} Result\n[{cit}] {title} - Evidence strength: {ev_str}/5"
                )

        if not parts:
            # Fallback to pre-computed RCS if no tool evidence
            parts.append("### Pre-computed Evidence (Fallback)")
            all_contexts = ctx.state.get("all_scored_contexts") or []
            for ctx_item in all_contexts[:10]:
                if hasattr(ctx_item, "summary"):
                    doc_cit_map = ctx.state.get("doc_citation_map", {})
                    cit = doc_cit_map.get(ctx_item.document_id, "?")
                    parts.append(
                        f"[{cit}] {ctx_item.summary[:200]}... (relevance: {ctx_item.relevance_score})"
                    )

        return "\n\n".join(parts) if parts else "No evidence available."

    def _extract_citations(self, content: str) -> List[int]:
        """Extract citation numbers from content.

        Args:
            content: Section content with [N] citations.

        Returns:
            List of unique citation numbers found.
        """
        import re

        pattern = r"\[(\d+)\]"
        matches = re.findall(pattern, content)
        return sorted(set(int(m) for m in matches))

    def _build_langfuse_config(self, run_name: str) -> Dict[str, Any]:
        """Build Langfuse config for LLM calls.

        Args:
            run_name: Name for the run.

        Returns:
            Config dictionary for LLM invoke.
        """
        handler = self.state.get("langfuse_handler")
        if not handler:
            return {}

        return {
            "callbacks": [handler],
            "tags": ["component:synthesis", "component:synthesis.agentic"],
            "run_name": run_name,
        }


async def generate_agentic_section(
    state: Dict[str, Any],
    section_name: str,
    section_instructions: str,
    additional_instructions: str = "",
) -> SectionOutput:
    """Generate a briefing section using the tool-augmented approach.

    Convenience function that creates an orchestrator and generates a section.

    Args:
        state: Synthesis state.
        section_name: Name of the section.
        section_instructions: Instructions for the section.
        additional_instructions: Extra formatting guidance.

    Returns:
        SectionOutput with content and verification status.
    """
    orchestrator = BriefingOrchestrator(state)
    return await orchestrator.generate_section(
        section_name=section_name,
        section_instructions=section_instructions,
        additional_instructions=additional_instructions,
    )
