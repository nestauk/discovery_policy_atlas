"""
Orchestrator for tool-augmented briefing generation.

Manages the interaction loop between the orchestrator LLM (gpt-5.2),
tool execution, section generation (gpt-5-mini), and verification.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal, Tuple

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.services.synthesis.schemas import RecommendationsOutput
from app.services.synthesis.utils import fetch_chunk_texts
from app.services.synthesis.tools.base import (
    get_tool_registry,
)
from app.services.synthesis.tools.models import (
    ORCHESTRATOR_MODEL,
    GENERATION_MODEL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured Output Schemas for Orchestrator Decisions
# ---------------------------------------------------------------------------


class ToolCallDecision(BaseModel):
    """A single tool call decision from the orchestrator."""

    tool: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )


class OrchestratorDecision(BaseModel):
    """Structured decision output from the orchestrator.

    Using Pydantic + with_structured_output() eliminates JSON parsing issues.
    """

    reasoning: str = Field(
        ..., description="Brief explanation of why these tools are being called"
    )
    tool_calls: List[ToolCallDecision] = Field(
        default_factory=list, description="List of tools to execute"
    )
    done: bool = Field(
        False, description="True when sufficient evidence has been gathered"
    )
    evidence_summary: Optional[str] = Field(
        None, description="Summary of evidence gathered (when done=True)"
    )


class ClaimQuoteResult(BaseModel):
    """Grounding result for a single (claim, citation) pair."""

    claim_text: str = Field(..., description="The claim text")
    citation_number: int = Field(..., description="Citation number [N] for this claim")
    is_supported: bool = Field(..., description="Whether the claim is supported")
    attribution: Literal["direct", "synthesised", "inferred"] = Field(
        ..., description="Attribution relationship between claim and source"
    )
    supporting_quote: str = Field(
        "", description="Verbatim supporting quote from source evidence"
    )
    chunk_id: str = Field("", description="Source chunk UUID for the quote")
    issue: Optional[str] = Field(
        None, description="Description of issue if not supported"
    )


class GroundingResult(BaseModel):
    """Structured grounding output."""

    claim_quotes: List[ClaimQuoteResult] = Field(
        default_factory=list, description="Per-claim grounding outcomes"
    )
    overall_supported: bool = Field(
        ..., description="Whether all claims are sufficiently supported"
    )
    issues_summary: Optional[str] = Field(None, description="Summary of issues if any")
    suggested_fixes: List[str] = Field(
        default_factory=list, description="Suggested fixes for unsupported claims"
    )


class InterventionTableRowOutput(BaseModel):
    """Structured output for a single interventions table row.

    The LLM provides prose per cell; we render the markdown table deterministically.
    """

    intervention_name: str = Field(
        ..., description="Short intervention category name (3-10 words)."
    )
    context: str = Field(
        ...,
        description="Context & Features cell prose (implementation setting, delivery, components).",
    )
    key_study_description: str = Field(
        ...,
        description=(
            "Key Study cell prose (concrete implementation example) with [N] citations."
        ),
    )
    impact_narrative: str = Field(
        ...,
        description=(
            "Impact & Outcomes cell prose. Must start with key-study outcomes/effect sizes (use "
            "get_top_studies.extracted_outcomes), then briefly summarise broader evidence in the theme."
        ),
    )
    sources: str = Field(
        ...,
        description="Sources cell: a compact list of [N] citations used across the row.",
    )


class InterventionsTableOutput(BaseModel):
    """Structured output for the interventions table section."""

    rows: List[InterventionTableRowOutput] = Field(
        ..., description="4-6 intervention rows for the interventions table."
    )


# Maximum tool calls per section (user-configured)
# Increased to support per-row evidence gathering for richer intervention tables.
MAX_TOOL_CALLS_PER_SECTION = 10


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
2. Use get_intervention_outcomes to get effect sizes, outcomes, and study types for interventions
3. Use get_top_studies to identify the strongest studies for a specific intervention category (ranked by evidence strength and predicted impact)
3. Use search_extractions for specific claims that need additional support
4. Use get_document_quality to verify source quality for key citations
5. Use get_citation_context to get full context for specific citations during verification
6. Stop when you have 3-5 high-quality evidence items per major claim

### Parameter Requirements (do not omit)
- get_theme_evidence: requires theme_name (string)
- get_multiple_document_quality: requires citation_numbers (array of ints)
- get_document_quality: requires citation_number (int)
- search_extractions: requires query (string)
- get_intervention_outcomes: optional intervention_name, otherwise fetch all
- get_top_studies: requires intervention_name (string)

### Efficiency
- You have a maximum of {max_tool_calls} tool calls per section
- Combine related queries where possible
- Don't repeat the same tool call

When you have gathered enough evidence, set done=True and provide an evidence_summary."""


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
    used_theme_names: set = field(default_factory=set)
    available_theme_names: List[str] = field(default_factory=list)
    available_citation_numbers: List[int] = field(default_factory=list)


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
    claim_quotes: List[ClaimQuoteResult] = Field(default_factory=list)
    tool_calls_made: int = 0


class BriefingOrchestrator:
    """Orchestrates tool-augmented briefing section generation.

    Uses a multi-phase approach:
    1. Evidence gathering (orchestrator decides which tools to call)
    2. Section generation (using gathered evidence)
    3. Grounding (checking claims against source evidence and extracting quotes)
    4. Iteration if grounding finds unsupported claims (up to 2 retries)
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
        )
        self.generation_llm = ChatOpenAI(
            model=GENERATION_MODEL,
        )

    def _emit_grounding_warning(self, section_name: str, issues: List[str]) -> None:
        """Emit grounding warnings to Langfuse handler when available."""
        message = (
            f"Grounding exhausted retries for section '{section_name}'. "
            f"Unsupported issues: {issues[:10]}"
        )
        logger.warning(message)

        handler = self.state.get("langfuse_handler")
        if not handler:
            return

        try:
            if hasattr(handler, "warning") and callable(handler.warning):
                handler.warning(message)
                return
            if hasattr(handler, "log") and callable(handler.log):
                handler.log(level="warning", message=message)
                return
            if hasattr(handler, "on_event") and callable(handler.on_event):
                handler.on_event(
                    {
                        "level": "warning",
                        "name": "grounding_retry_exhausted",
                        "message": message,
                    }
                )
        except Exception as e:
            logger.debug(f"Langfuse warning emission failed: {e}")

    async def generate_section(
        self,
        section_name: str,
        section_instructions: str,
        additional_instructions: str = "",
        max_retries: int = 2,
    ) -> SectionOutput:
        """Generate a briefing section with tool-augmented evidence.

        Uses soft grounding - content is always returned even if
        grounding flags unsupported claims after retries.

        Args:
            section_name: Name of the section (e.g., "Background").
            section_instructions: What the section should cover.
            additional_instructions: Extra formatting/content guidance.
            max_retries: Max grounding retry attempts.

        Returns:
            SectionOutput with content, grounding status, and claim-level quotes.
        """
        ctx = OrchestratorContext(
            state=self.state,
            section_name=section_name,
            section_instructions=section_instructions,
        )

        # Phase 1: Gather evidence
        if ctx.section_name.lower().startswith("policy interventions analysis"):
            # Interventions table benefits from row-by-row evidence gathering.
            await self._gather_interventions_table_evidence(ctx)
        else:
            await self._gather_evidence(ctx)

        # Phase 2: Generate content
        content = await self._generate_section_content(
            ctx,
            additional_instructions,
        )

        # Extract citations used
        citations_used = self._extract_citations(content)

        # Phase 3: Grounding + quote extraction with retry loop
        grounding = await self._ground_and_extract_quotes(ctx, content)
        verification_passed = grounding.overall_supported
        verification_issues = list(grounding.suggested_fixes or [])

        retries_remaining = max_retries
        while not verification_passed and retries_remaining > 0:
            logger.info(
                f"Section '{section_name}' grounding had issues, retrying: "
                f"{grounding.issues_summary or 'unsupported claims detected'}"
            )
            unsupported = [cq for cq in grounding.claim_quotes if not cq.is_supported]
            retry_issues = [
                f"Claim: {cq.claim_text} [citation {cq.citation_number}] - {cq.issue or 'Not supported by source evidence'}"
                for cq in unsupported
            ]
            verification_issues = retry_issues or verification_issues
            ctx.gathered_evidence.append(
                {
                    "tool": "verification_feedback",
                    "issues": verification_issues,
                    "claims_to_fix": [cq.model_dump() for cq in unsupported],
                }
            )
            content = await self._generate_section_content(ctx, additional_instructions)
            citations_used = self._extract_citations(content)
            grounding = await self._ground_and_extract_quotes(ctx, content)
            verification_passed = grounding.overall_supported
            verification_issues = list(grounding.suggested_fixes or verification_issues)
            retries_remaining -= 1

        if not verification_passed:
            self._emit_grounding_warning(section_name, verification_issues)

        # Always return content - verification is informational only
        return SectionOutput(
            content=content,
            citations_used=citations_used,
            verification_passed=verification_passed,
            verification_issues=verification_issues,
            claim_quotes=grounding.claim_quotes,
            tool_calls_made=ctx.tool_call_count,
        )

    async def _gather_evidence(self, ctx: OrchestratorContext) -> None:
        """Use orchestrator LLM with structured output to decide which tools to call.

        Args:
            ctx: Orchestrator context to update with evidence.
        """
        import json

        # Build tool descriptions
        tool_descriptions = self._build_tool_descriptions()

        # Collect theme names by branch. Phase-1 tool auto-fill must be branch-aware
        # to avoid passing issue/outcome names into intervention-evidence tools.
        intervention_theme_names: List[str] = []
        issue_theme_names: List[str] = []
        outcome_theme_names: List[str] = []

        for t in self.state.get("final_intervention_themes") or []:
            name = getattr(t, "name", None) or getattr(t, "theme_name", None)
            if name and name not in intervention_theme_names:
                intervention_theme_names.append(name)

        for t in self.state.get("final_issue_themes") or []:
            name = getattr(t, "name", None) or getattr(t, "theme_name", None)
            if name and name not in issue_theme_names:
                issue_theme_names.append(name)

        for t in self.state.get("final_outcome_themes") or []:
            name = getattr(t, "name", None) or getattr(t, "theme_name", None)
            if name and name not in outcome_theme_names:
                outcome_theme_names.append(name)

        # Default theme list (used only when we cannot infer branch intent)
        theme_names: List[str] = (
            intervention_theme_names + issue_theme_names + outcome_theme_names
        )

        grounded_citations = self.state.get("grounded_citations") or []
        citation_numbers = [
            getattr(c, "citation_number", None)
            for c in grounded_citations
            if getattr(c, "citation_number", None)
        ]

        # Collect available intervention category names (for parameter auto-fill)
        intervention_names: List[str] = []
        aggregated_interventions = self.state.get("aggregated_interventions") or []
        for it in aggregated_interventions:
            name = getattr(it, "intervention_name", None)
            if name and name not in intervention_names:
                intervention_names.append(name)

        # Build system prompt
        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
            tool_descriptions=tool_descriptions,
            max_tool_calls=ctx.max_tool_calls,
        )

        def _prepare_arguments(
            tool_name: str, arguments: Dict[str, Any]
        ) -> Optional[Dict[str, Any]]:
            """Normalise and auto-fill tool arguments; return None to skip."""
            args = dict(arguments or {})

            if tool_name == "get_theme_evidence" and not args.get("theme_name"):
                sec = (ctx.section_name or "").lower()
                if "outcome" in sec:
                    candidates = outcome_theme_names
                elif "issue" in sec or "challenge" in sec or "barrier" in sec:
                    candidates = issue_theme_names
                elif "intervention" in sec or "recommendation" in sec:
                    candidates = intervention_theme_names
                else:
                    candidates = intervention_theme_names or theme_names

                next_theme = None
                for name in candidates:
                    if name not in ctx.used_theme_names:
                        next_theme = name
                        break
                if next_theme:
                    args["theme_name"] = next_theme
                    ctx.used_theme_names.add(next_theme)
                    logger.info(
                        f"Auto-filled get_theme_evidence theme_name={next_theme}"
                    )
                else:
                    logger.warning("Skipping get_theme_evidence: missing theme_name")
                    return None

            if tool_name == "get_multiple_document_quality" and not args.get(
                "citation_numbers"
            ):
                logger.warning(
                    "Skipping get_multiple_document_quality: missing citation_numbers"
                )
                return None

            if tool_name == "get_document_quality" and not args.get("citation_number"):
                if citation_numbers:
                    args["citation_number"] = citation_numbers[0]
                    logger.info(
                        f"Auto-filled get_document_quality with citation_number={citation_numbers[0]}"
                    )
                else:
                    logger.warning(
                        "Skipping get_document_quality: missing citation_number"
                    )
                    return None

            if tool_name == "search_extractions" and not args.get("query"):
                logger.warning("Skipping search_extractions: missing query")
                return None

            if tool_name == "get_citation_context" and not args.get("citation_number"):
                if citation_numbers:
                    args["citation_number"] = citation_numbers[0]
                    logger.info(
                        f"Auto-filled get_citation_context with citation_number={citation_numbers[0]}"
                    )
                else:
                    logger.warning(
                        "Skipping get_citation_context: missing citation_number"
                    )
                    return None

            if tool_name == "get_top_studies" and not args.get("intervention_name"):
                next_intervention = None
                for name in intervention_names:
                    if name not in ctx.used_theme_names:
                        next_intervention = name
                        break
                if next_intervention:
                    args["intervention_name"] = next_intervention
                    ctx.used_theme_names.add(next_intervention)
                    logger.info(
                        f"Auto-filled get_top_studies intervention_name={next_intervention}"
                    )
                else:
                    logger.warning(
                        "Skipping get_top_studies: missing intervention_name"
                    )
                    return None

            return args

        # Initial user message
        user_message = f"""## Section: {ctx.section_name}
{ctx.section_instructions}

## Pre-computed Evidence Available
- {len(self.state.get("scored_theme_evidence", []))} theme evidence sets
- {len(self.state.get("scored_issue_evidence", []))} issue evidence sets
- {len(self.state.get("grounded_citations", []))} grounded citations
- {len(self.state.get("all_scored_contexts", []))} total scored contexts

Available theme names: {", ".join(theme_names) if theme_names else "None"}
Available intervention names: {", ".join(intervention_names) if intervention_names else "None"}
Available citation numbers: {citation_numbers if citation_numbers else "None"}

Decide which tools to call to gather the most relevant evidence for this section."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Create structured output LLM for orchestrator decisions
        # Use function_calling method as Dict[str, Any] isn't compatible with
        # OpenAI's strict JSON schema mode (requires additionalProperties: false)
        structured_orchestrator = self.orchestrator_llm.with_structured_output(
            OrchestratorDecision,
            method="function_calling",
        )

        # Orchestrator loop
        while ctx.tool_call_count < ctx.max_tool_calls:
            # Get LLM decision using structured output (guaranteed valid schema)
            config = self._build_langfuse_config("orchestrator_decide")
            try:
                decision: OrchestratorDecision = await structured_orchestrator.ainvoke(
                    messages, config=config
                )
            except Exception as e:
                logger.warning(f"Orchestrator structured output failed: {e}")
                break

            # Check if done
            if decision.done:
                logger.info(
                    f"Orchestrator done gathering evidence: {decision.reasoning}"
                )
                break

            # Execute tool calls
            if not decision.tool_calls:
                break

            tool_results: List[Dict[str, Any]] = []
            for tc in decision.tool_calls:
                if ctx.tool_call_count >= ctx.max_tool_calls:
                    break

                tool_name = tc.tool
                arguments = _prepare_arguments(tool_name, tc.arguments or {})

                # Phase 1 is evidence gathering only. Grounding is handled separately
                # in `_ground_and_extract_quotes()`; do not allow verification tools here even if
                # the LLM attempts to call them.
                if tool_name in {"verify_claim_support", "verify_multiple_claims"}:
                    logger.warning(
                        f"Skipping {tool_name}: verification tools are not allowed during evidence gathering"
                    )
                    continue
                if arguments is None:
                    continue

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

            # Add tool results to conversation for next iteration
            # Serialize the decision for the assistant message
            decision_dict = decision.model_dump()
            results_summary = json.dumps(tool_results, indent=2, default=str)
            messages.append({"role": "assistant", "content": json.dumps(decision_dict)})
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool results:\n{results_summary}\n\nDecide next action.",
                }
            )

        logger.info(
            f"Evidence gathering complete: {ctx.tool_call_count} tool calls, "
            f"{len(ctx.gathered_evidence)} evidence items"
        )

    async def _gather_interventions_table_evidence(
        self, ctx: OrchestratorContext
    ) -> None:
        """Gather evidence for interventions table, separately per row.

        This ensures the generator has distinct evidence blocks for each intervention row,
        rather than relying on a single aggregate tool call.
        """
        # Increase tool-call budget for this section to allow per-row retrieval.
        ctx.max_tool_calls = max(ctx.max_tool_calls, 25)

        # 1) Get the top intervention categories (sorted by frequency by the tool)
        base = await self.registry.execute(
            "get_intervention_outcomes", ctx.state, max_results=10
        )
        ctx.tool_call_count += 1
        if base.success and base.data:
            ctx.gathered_evidence.append(
                {"tool": "get_intervention_outcomes", "data": base.data}
            )
        else:
            logger.warning(
                f"Interventions evidence gather failed at baseline: {base.error or 'no data'}"
            )
            return

        outcomes: List[Dict[str, Any]] = (
            base.data if isinstance(base.data, list) else []
        )
        if not outcomes:
            return

        desired_rows = min(6, max(4, len(outcomes)))
        selected = outcomes[:desired_rows]

        # 2) For each row, gather evidence separately
        for item in selected:
            if ctx.tool_call_count >= ctx.max_tool_calls:
                break

            intervention_name = (item.get("intervention_name") or "").strip()
            if not intervention_name:
                continue

            # Per-row aggregated outcomes
            res_out = await self.registry.execute(
                "get_intervention_outcomes",
                ctx.state,
                intervention_name=intervention_name,
                max_results=1,
            )
            ctx.tool_call_count += 1
            if res_out.success and res_out.data:
                ctx.gathered_evidence.append(
                    {"tool": "get_intervention_outcomes", "data": res_out.data}
                )

            if ctx.tool_call_count >= ctx.max_tool_calls:
                break

            # Per-row key studies (ranked by doc_scores)
            res_top = await self.registry.execute(
                "get_top_studies",
                ctx.state,
                intervention_name=intervention_name,
                max_results=2,
            )
            ctx.tool_call_count += 1
            if res_top.success and res_top.data:
                ctx.gathered_evidence.append(
                    {"tool": "get_top_studies", "data": res_top.data}
                )

            if ctx.tool_call_count >= ctx.max_tool_calls:
                break

            # Per-row delivery/subgroup enrichment (optional)
            res_details = await self.registry.execute(
                "get_intervention_details",
                ctx.state,
                intervention_name=intervention_name,
                max_results=1,
            )
            ctx.tool_call_count += 1
            if res_details.success and res_details.data:
                ctx.gathered_evidence.append(
                    {"tool": "get_intervention_details", "data": res_details.data}
                )

        logger.info(
            f"Interventions evidence gathering complete: {ctx.tool_call_count} tool calls, "
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
        # Special-case recommendations to enforce structured output
        if ctx.section_name.lower().startswith("policy recommendation"):
            return await self._generate_recommendations_structured(
                ctx, additional_instructions
            )

        # Special-case interventions table: structured output + deterministic table rendering
        if ctx.section_name.lower().startswith("policy interventions analysis"):
            return await self._generate_interventions_table_structured(
                ctx, additional_instructions
            )

        # Build evidence context
        evidence_context = await self._format_evidence_for_generation(ctx)

        prompt = SECTION_GENERATION_PROMPT.format(
            section_name=ctx.section_name,
            section_instructions=ctx.section_instructions,
            evidence_context=evidence_context,
            additional_instructions=additional_instructions,
        )

        config = self._build_langfuse_config("generate_section")
        response = await self.generation_llm.ainvoke(prompt, config=config)

        return response.content.strip()

    async def _generate_interventions_table_structured(
        self,
        ctx: OrchestratorContext,
        additional_instructions: str,
    ) -> str:
        """Generate interventions table using structured output then render deterministically."""
        evidence_context = await self._format_evidence_for_generation(ctx)

        prompt = f"""
You are writing the "Key Interventions" table for an executive policy briefing.

Output requirements:
- Produce exactly a markdown table with header:
  | Intervention | Context & Features | Key Study | Impact & Outcomes | Sources |
- The content for each cell MUST be produced via the structured schema (rows), then the system will render the table.

Row requirements (4-6 rows):
- Intervention: short, plain category label (not a paragraph).
- Context & Features: concise implementation details (setting, delivery, components).
- Key Study: concrete implementation example drawn from get_top_studies. Include concise implementation details (setting, delivery, components). Name country(s)/location that the study took place in if available. Include [N] citations. 
- Impact & Outcomes:
  - Start with key-study outcomes/effect sizes using get_top_studies.extracted_outcomes.
  - If extracted_outcomes contains any non-empty effect_size values, you MUST include at least one effect_size verbatim (e.g., "15.01%") and name the outcome_variable.
  - If effect_size is empty but extracted_outcomes includes numeric details in result_text or supporting_quote, include at least one concrete number from those fields.
  - If no numerical details are available, include at least one non-numerical detail from the extracted_outcomes.
  - Then add 1-2 sentences on broader evidence in the theme (direction, consistency, caveats).
  - Include [N] citations for both the key-study outcomes and the broader evidence statements.
- Sources: compact [N] citations used in the row (deduplicate).

Citation rules:
- ONLY use [N] citations from Evidence below.
- Do not invent citation numbers.

Evidence:
{evidence_context}

Additional guidance:
{additional_instructions}
"""

        structured_llm = self.generation_llm.with_structured_output(
            InterventionsTableOutput,
            method="function_calling",
        )
        config = self._build_langfuse_config("generate_interventions_table_structured")
        result: InterventionsTableOutput = await structured_llm.ainvoke(
            prompt, config=config
        )

        # Deterministic markdown rendering (avoid LLM table formatting failures)
        lines: List[str] = []
        lines.append(
            "| Intervention | Context & Features | Key Study | Impact & Outcomes | Sources |"
        )
        lines.append("|---|---|---|---|---|")
        for r in result.rows:
            # Replace newlines inside cells to keep markdown stable; use <br/>-like via newline escaped
            def _cell(s: str) -> str:
                s = (s or "").strip()
                return s.replace("\n", "<br/><br/>")

            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(r.intervention_name),
                        _cell(r.context),
                        _cell(r.key_study_description),
                        _cell(r.impact_narrative),
                        _cell(r.sources),
                    ]
                )
                + " |"
            )
        return "\n".join(lines).strip()

    def _extract_claim_citation_pairs(
        self, content: str
    ) -> List[Tuple[str, List[int]]]:
        """Extract claim/citation pairs from generated section content."""
        claims: List[Tuple[str, List[int]]] = []
        seen: set = set()
        for sentence in re.findall(r"[^.!?\n]*\[\d+\][^.!?\n]*[.!?]?", content):
            claim_text = sentence.strip()
            if not claim_text:
                continue
            citations = sorted({int(x) for x in re.findall(r"\[(\d+)\]", claim_text)})
            if not citations:
                continue
            key = (claim_text, tuple(citations))
            if key in seen:
                continue
            seen.add(key)
            claims.append((claim_text, citations))
        return claims

    def _section_grounding_guidance(self, section_name: str) -> str:
        """Return section-aware grounding guidance."""
        section_lower = section_name.lower()
        if "recommendation" in section_lower:
            return (
                "Recommendation section: inferred attributions are common when claims "
                "logically extrapolate from the evidence."
            )
        if "synthesis" in section_lower:
            return "Synthesis section: a mix of direct and synthesised attributions is expected."
        return (
            "Factual section: expect mostly direct attributions unless the claim explicitly "
            "combines multiple sources."
        )

    async def _ground_and_extract_quotes(
        self,
        ctx: OrchestratorContext,
        content: str,
    ) -> GroundingResult:
        """Verify claims against source text and extract per-claim supporting quotes."""
        claim_pairs = self._extract_claim_citation_pairs(content)
        if not claim_pairs:
            return GroundingResult(
                claim_quotes=[],
                overall_supported=True,
                issues_summary=None,
                suggested_fixes=[],
            )

        citation_by_number = {
            getattr(c, "citation_number", 0): c
            for c in (ctx.state.get("grounded_citations") or [])
            if getattr(c, "citation_number", 0)
        }
        all_contexts = ctx.state.get("all_scored_contexts") or []
        extraction_quotes = ctx.state.get("extraction_quotes") or {}

        citation_to_claims: Dict[int, List[str]] = {}
        for claim_text, citations in claim_pairs:
            for citation_number in citations:
                citation_to_claims.setdefault(citation_number, []).append(claim_text)

        collected: List[ClaimQuoteResult] = []
        suggested_fixes: List[str] = []
        issue_messages: List[str] = []
        structured_grounder = self.generation_llm.with_structured_output(
            GroundingResult,
            method="function_calling",
        )

        for citation_number, claims_for_citation in citation_to_claims.items():
            citation = citation_by_number.get(citation_number)
            if citation is None:
                for claim_text in claims_for_citation:
                    collected.append(
                        ClaimQuoteResult(
                            claim_text=claim_text,
                            citation_number=citation_number,
                            is_supported=False,
                            attribution="direct",
                            supporting_quote="",
                            chunk_id="",
                            issue="Citation not found in grounded citation map.",
                        )
                    )
                suggested_fixes.append(
                    f"Replace or remove unavailable citation [{citation_number}] for affected claims."
                )
                continue

            doc_id = citation.analysis_document_id
            doc_chunk_ids = [
                context.chunk_id
                for context in all_contexts
                if context.document_id == doc_id and context.chunk_id
            ]
            chunk_text_map = await fetch_chunk_texts(doc_chunk_ids)
            chunk_blocks = []
            for chunk_id in doc_chunk_ids[:12]:
                chunk_text = chunk_text_map.get(chunk_id, "")
                if chunk_text:
                    chunk_blocks.append(f"- chunk_id={chunk_id}\n  text={chunk_text}")

            extraction_quote_blocks = [
                f"- {q}" for q in (extraction_quotes.get(doc_id) or [])[:12] if q
            ]
            claims_block = "\n".join(f"- {c}" for c in claims_for_citation)
            source_block = (
                "\n".join(chunk_blocks + extraction_quote_blocks) or "- (none)"
            )

            prompt = (
                "You are grounding policy claims against source evidence.\n\n"
                f"Section: {ctx.section_name}\n"
                f"{self._section_grounding_guidance(ctx.section_name)}\n\n"
                "A claim is supported if the source text contains relevant evidence that "
                "reasonably underpins the claim (direct, synthesised, or inferred).\n"
                "- direct: source alone substantiates the specific claim.\n"
                "- synthesised: source contributes evidence but claim needs multiple sources.\n"
                "- inferred: source provides premises and claim extrapolates beyond explicit text.\n"
                "Mark unsupported only when this source provides no relevant evidence.\n\n"
                f"Citation number: [{citation_number}]\n"
                f"Document title: {citation.title or 'Unknown'}\n"
                "Claims to assess:\n"
                f"{claims_block}\n\n"
                "Available source evidence (verbatim text):\n"
                f"{source_block}\n\n"
                "Return one claim_quotes entry per claim. "
                "supporting_quote must be verbatim from the source text (<=200 chars). "
                "chunk_id should match the supporting chunk when available."
            )

            try:
                result: GroundingResult = await structured_grounder.ainvoke(
                    prompt,
                    config=self._build_langfuse_config(
                        f"ground_section_citation_{citation_number}"
                    ),
                )
                # Normalise citation_number per grouped call.
                returned_claims = {
                    item.claim_text.strip() for item in result.claim_quotes
                }
                for item in result.claim_quotes:
                    collected.append(
                        ClaimQuoteResult(
                            claim_text=item.claim_text,
                            citation_number=citation_number,
                            is_supported=item.is_supported,
                            attribution=item.attribution,
                            supporting_quote=item.supporting_quote,
                            chunk_id=item.chunk_id,
                            issue=item.issue,
                        )
                    )
                for claim_text in claims_for_citation:
                    if claim_text.strip() not in returned_claims:
                        collected.append(
                            ClaimQuoteResult(
                                claim_text=claim_text,
                                citation_number=citation_number,
                                is_supported=False,
                                attribution="direct",
                                supporting_quote="",
                                chunk_id="",
                                issue=(
                                    "Grounding output omitted this claim; treated as unsupported."
                                ),
                            )
                        )
                        suggested_fixes.append(
                            f"Re-ground omitted claim for citation [{citation_number}]."
                        )
                if result.suggested_fixes:
                    suggested_fixes.extend(result.suggested_fixes)
                if result.issues_summary:
                    issue_messages.append(result.issues_summary)
            except Exception as e:
                logger.warning(
                    f"Grounding failed for citation [{citation_number}]: {e}"
                )
                for claim_text in claims_for_citation:
                    collected.append(
                        ClaimQuoteResult(
                            claim_text=claim_text,
                            citation_number=citation_number,
                            is_supported=False,
                            attribution="direct",
                            supporting_quote="",
                            chunk_id="",
                            issue="Grounding call failed; unable to verify against source evidence.",
                        )
                    )
                suggested_fixes.append(
                    f"Re-ground claim(s) citing [{citation_number}] due to grounding tool failure."
                )

        overall_supported = all(item.is_supported for item in collected)
        if not overall_supported:
            for item in collected:
                if not item.is_supported:
                    issue_messages.append(
                        f"[{item.citation_number}] {item.claim_text}: {item.issue or 'Unsupported'}"
                    )

        return GroundingResult(
            claim_quotes=collected,
            overall_supported=overall_supported,
            issues_summary="\n".join(issue_messages) if issue_messages else None,
            suggested_fixes=list(dict.fromkeys(suggested_fixes)),
        )

    def _build_tool_descriptions(self) -> str:
        """Build formatted tool descriptions for the orchestrator.

        Returns:
            Formatted string of tool descriptions.
        """
        # Phase 1 is evidence gathering only. Grounding is handled separately
        # in `_ground_and_extract_quotes()` using structured output.
        excluded_tools = {
            "verify_claim_support",
            "verify_multiple_claims",
            # Avoid wasted calls: this is redundant with other evidence outputs and is
            # frequently auto-filled with broad citation ranges when present.
            "get_multiple_document_quality",
        }
        tools = [t for t in self.registry.get_all() if t.name not in excluded_tools]
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

    async def _format_evidence_for_generation(self, ctx: OrchestratorContext) -> str:
        """Format gathered evidence for the generation prompt.

        Args:
            ctx: Context with gathered evidence.

        Returns:
            Formatted evidence string.
        """
        parts: List[str] = []
        all_chunk_ids: List[str] = []
        for ev in ctx.gathered_evidence:
            data = ev.get("data", {})
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        chunk_id = str(item.get("chunk_id") or "")
                        if chunk_id:
                            all_chunk_ids.append(chunk_id)
            elif isinstance(data, dict):
                chunk_id = str(data.get("chunk_id") or "")
                if chunk_id:
                    all_chunk_ids.append(chunk_id)
        chunk_text_map = await fetch_chunk_texts(all_chunk_ids)

        # Build citation map fallback if missing
        doc_citation_map = ctx.state.get("doc_citation_map") or {}
        if not doc_citation_map:
            grounded = ctx.state.get("grounded_citations") or []
            for cit in grounded:
                if getattr(cit, "analysis_document_id", None) and getattr(
                    cit, "citation_number", None
                ):
                    doc_citation_map[cit.analysis_document_id] = cit.citation_number

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
                        chunk_id = str(item.get("chunk_id") or "")
                        source_text = (
                            chunk_text_map.get(chunk_id)
                            or str(item.get("chunk_text") or "")
                            or str(item.get("key_context_chunk_text") or "")
                            or str(item.get("content") or "")
                        )
                        if tool == "get_intervention_outcomes":
                            # Rich formatting for aggregated intervention outcomes
                            name = item.get("intervention_name", "Unknown")
                            effect = item.get("effect_consensus", "Unknown")
                            samples = item.get("sample_effect_sizes") or []
                            samples_str = "; ".join(samples[:2]) if samples else "n/a"
                            study_types = item.get("study_types") or {}
                            top_study = (
                                sorted(
                                    study_types.items(),
                                    key=lambda kv: kv[1],
                                    reverse=True,
                                )[0][0]
                                if study_types
                                else "Unknown"
                            )
                            related_outcomes = item.get("related_outcomes") or []
                            related_str = ", ".join(related_outcomes[:2]) or "n/a"
                            freq = item.get("frequency", 0)
                            items.append(
                                f"{name}: effect={effect}; effects={samples_str}; outcomes={related_str}; studies={freq}; top study type={top_study}"
                            )
                        elif tool == "get_top_studies":
                            cit_raw = item.get("citation_number")
                            cit = (
                                str(cit_raw)
                                if isinstance(cit_raw, int) and cit_raw > 0
                                else None
                            )
                            title = item.get("title", "Unknown")
                            evs = item.get("evidence_strength", "?")
                            imp = item.get("impact_score", "?")
                            rel = item.get("relevance_score", "?")
                            summary = item.get("key_context_summary") or ""
                            prefix = f"[{cit}] " if cit else ""
                            items.append(
                                f"{prefix}({title}; evidence={evs}/5, impact={imp}/5, relevance={rel})\n"
                                f"  Summary: {summary}\n"
                                f"  Source text: {source_text}"
                            )
                        else:
                            cit = item.get("citation_number", "?")
                            summary = item.get("summary", item.get("content", ""))
                            title = item.get("document_title", "Unknown")
                            rel = item.get(
                                "relevance_score", item.get("similarity_score", "?")
                            )
                            items.append(
                                f"[{cit}] ({title}; relevance: {rel})\n"
                                f"  Summary: {summary}\n"
                                f"  Source text: {source_text}"
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
            fallback_chunk_text_map = await fetch_chunk_texts(
                [
                    ctx_item.chunk_id
                    for ctx_item in all_contexts[:10]
                    if ctx_item.chunk_id
                ]
            )
            for ctx_item in all_contexts[:10]:
                if hasattr(ctx_item, "summary"):
                    doc_cit_map = doc_citation_map or ctx.state.get(
                        "doc_citation_map", {}
                    )
                    cit = doc_cit_map.get(ctx_item.document_id, "?")
                    source_text = fallback_chunk_text_map.get(ctx_item.chunk_id, "")
                    parts.append(
                        f"[{cit}] (relevance: {ctx_item.relevance_score})\n"
                        f"  Summary: {ctx_item.summary}\n"
                        f"  Source text: {source_text}"
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

    async def _generate_recommendations_structured(
        self,
        ctx: OrchestratorContext,
        additional_instructions: str,
    ) -> str:
        """Generate recommendations using structured output to ensure format consistency."""
        evidence_context = await self._format_evidence_for_generation(ctx)

        prompt = f"""
You are writing policy recommendations for UK cabinet ministers.

Requirements:
- Output exactly 3-4 recommendations.
- Each recommendation must include: number (1..4), title (3-7 words, action-led), description (60-90 words), implementation_option (25-60 words), citation_numbers.
- Title must be plain text only: do NOT include markdown (no *, **, _, backticks) or trailing punctuation.
- Description must be evidence-backed and use inline [N] citations; citation_numbers list must match the numbers used across BOTH description and implementation_option.
- At least one citation per recommendation. No '?' citations.
- British English. Concise and specific.
- implementation_option must be explicitly framed as an option/suggestion (conditional language) and must not claim it is directly proven if it is an extrapolation.

Evidence (use only these citations):
{evidence_context}

Additional guidance:
{additional_instructions}
"""

        structured_llm = self.generation_llm.with_structured_output(
            RecommendationsOutput,
            method="function_calling",
        )
        config = self._build_langfuse_config("generate_recommendations_structured")
        result = await structured_llm.ainvoke(prompt, config=config)

        # Convert structured output to a numbered list compatible with parser (avoid markdown in titles)
        lines: List[str] = []
        for rec in result.recommendations:
            title = (rec.title or "").strip().strip("*").strip()
            impl = (getattr(rec, "implementation_option", "") or "").strip()
            if impl:
                lines.append(
                    f"{rec.number}. {title}: {rec.description}\nImplementation option: {impl}"
                )
            else:
                lines.append(f"{rec.number}. {title}: {rec.description}")
        return "\n".join(lines)


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
