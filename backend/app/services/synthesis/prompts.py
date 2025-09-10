from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate


def build_discover_themes_prompt() -> ChatPromptTemplate:
    """Prompt for discovering themes from concept descriptions.

    Returns:
        ChatPromptTemplate: Template expecting variables: instructions, concepts
    """
    system = "You are a senior research analyst at Nesta. Identify the natural thematic structure in the provided concepts."
    user = "{instructions}\n\n" "CONCEPTS:\n{concepts}"
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def make_discover_themes_instructions(critique: Optional[str]) -> str:
    """Compose the instruction text for theme discovery, including optional critique.

    Args:
        critique: Optional critique text from a previous attempt.

    Returns:
        str: Instruction text to use with the discover themes prompt.
    """
    critique_prompt_addition = (
        f"You must address the following critique of your previous attempt: {critique}"
        if critique
        else ""
    )
    return (
        "Follow these principles: 1) Exhaustiveness; 2) Mutual Exclusivity; 3) Appropriate Granularity.\n"
        f"{critique_prompt_addition}\n"
        "Return a structured list of themes with name and description only."
    )


def build_theme_critique_prompt(entity: str) -> ChatPromptTemplate:
    """Prompt for critiquing discovered themes.

    Args:
        entity: Either "issue" or "intervention" to tailor wording.

    Returns:
        ChatPromptTemplate: Template expecting variable: themes
    """
    system = "You return STRICT TEXT only: either 'None' or a concise list of changes."
    user = (
        f"Assess {entity} themes against: Exhaustiveness, Mutual Exclusivity, Appropriate Granularity.\n"
        "If acceptable, reply exactly 'None'. Otherwise, list concise edits.\n\n"
        "Themes: {themes}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_classify_concept_prompt() -> ChatPromptTemplate:
    """Prompt for classifying a single concept into one of the provided themes.

    Returns:
        ChatPromptTemplate: Template expecting variables: themes, concept
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", "Return only the number."),
            (
                "user",
                "Classify the concept to the single best matching theme. Respond ONLY with the theme number (e.g., 1). No words.\n\n"
                "Themes:\n{themes}\n\nConcept:\n{concept}",
            ),
        ]
    )


def build_impact_summary_prompt() -> ChatPromptTemplate:
    """Prompt for writing a short impact summary for a theme.

    Returns:
        ChatPromptTemplate: Template expecting variables: name, sample
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", "Write a 35–45 word impact summary, plain text."),
            (
                "user",
                "Theme: {name}\nRepresentative concepts:\n{sample}\nSummarise expected impacts and effectiveness; British English.",
            ),
        ]
    )


def build_executive_briefing_prompt() -> ChatPromptTemplate:
    """Prompt for synthesising the final executive briefing.

    Returns:
        ChatPromptTemplate: Template expecting variables: rq, payload
    """
    system = "You are a senior UK policy advisor. Return plaintext only (no markdown)."
    user = (
        "Write a concise executive briefing (2 short paragraphs).\n"
        "- Directly answer the research question.\n"
        "- Distinguish clearly between Key Challenges (issues) and Recommended Interventions.\n"
        "- Close with a high-level assessment of the evidence base.\n\n"
        "Research question: {rq}\n"
        "Structured data: {payload}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])
