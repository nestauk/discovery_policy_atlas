from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate


def build_discover_themes_prompt() -> ChatPromptTemplate:
    """Prompt for discovering themes from concept descriptions, guided by a research question.

    Returns:
        ChatPromptTemplate: Template expecting variables: critique_instruction, rq, concepts
    """
    system = (
        "You are an expert in qualitative data analysis, specialising in synthesising "
        "complex information for senior UK policymakers. Your core skill is to identify "
        "a clear, logical, and insightful thematic structure from diverse sources."
    )
    user = (
        "<role>\n"
        "You are an expert in qualitative data analysis, specialising in synthesising complex information for senior UK policymakers. "
        "Your core skill is to identify a clear, logical, and insightful thematic structure from diverse sources.\n"
        "</role>\n"
        "<task>\n"
        "Guided by the user's RESEARCH QUESTION, analyse the provided JSON array of CONCEPTS to define the most logical set of thematic groups. "
        "The primary goal is to create a structure that is directly relevant to answering the research question.\n"
        "</task>\n"
        "<methodology>\n"
        "Follow this three-step process:\n\n"
        "Initial Draft: Review all concepts to draft an initial set of themes relevant to the research question.\n\n"
        "Critical Review: Systematically challenge the draft themes against every constraint below, especially 'Collectively Exhaustive' and 'Mutually Exclusive'.\n\n"
        "Finalise: Refine the theme names, descriptions, and groupings based on the critical review to produce the final, most logical structure.\n"
        "</methodology>\n"
        "<constraints>\n\n"
        "Collectively Exhaustive: Every concept must be categorised into a theme. The set of themes must fully cover all provided concepts.\n\n"
        "Mutually Exclusive: Themes must be conceptually distinct with minimal overlap. A concept should not fit equally well into multiple themes.\n\n"
        "Meaningful Granularity: The final structure must be the most logical grouping possible. While most themes will group multiple concepts, "
        "a single, highly distinct concept can form its own theme if it does not logically fit with others.\n\n"
        "Affirmative Summarisation: Theme descriptions must be affirmative, directly stating what the theme is about. "
        "Do not describe what a theme is not or use meta-language like 'This theme covers...'.\n\n"
        "Evidence Grounding: You must derive themes exclusively from the information within the provided JSON CONCEPTS data. Do not introduce outside knowledge.\n"
        "{critique_instruction}\n"
        "</constraints>\n"
        "<output_format>\n"
        'Return a single JSON object. The object must contain a single key, "themes", which is a list of objects. '
        'Each object in the list must have two string keys: "theme_name" and "theme_description".\n'
        "</output_format>\n\n"
        "RESEARCH QUESTION:\n{rq}\n\n"
        "CONCEPTS:\n{concepts}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def make_discover_themes_instructions(critique: Optional[str]) -> str:
    """Compose the critique insertion for the discover themes constraints.

    Args:
        critique: Optional critique text from a previous attempt.

    Returns:
        str: Critique instruction snippet to interpolate into the constraints section.
    """
    if critique:
        return (
            "Critique to address: You must address the following critique from a previous attempt: "
            f"{critique}"
        )
    return ""


def build_theme_critique_prompt(entity: str) -> ChatPromptTemplate:
    """Prompt for critiquing discovered themes against strict criteria.

    Args:
        entity: Maintained for compatibility; wording is universal.

    Returns:
        ChatPromptTemplate: Template expecting variables: rq, themes
    """
    system = (
        "You are a Quality Assurance Analyst. You critically evaluate thematic structures "
        "against a defined set of rules. Be logical and precise. Output must strictly follow the output rules."
    )
    user = (
        "<role>\n"
        "You are a Quality Assurance Analyst. Your sole function is to critically evaluate a thematic structure against a defined set of rules. "
        "You are logical, precise, and your output is strictly formatted.\n"
        "</role>\n"
        "<task>\n"
        "Critically assess the provided thematic structure against the evaluation criteria below. You must consider the themes' relevance to the user's RESEARCH QUESTION. "
        "Your goal is to identify any violations of the criteria and provide specific, actionable feedback for improvement.\n"
        "</task>\n"
        "<evaluation_criteria>\n\n"
        "Relevance to Research Question: The themes must be a useful and direct way to structure an answer to the user's research question.\n\n"
        "Collectively Exhaustive: The themes must fully cover all potential concepts related to the research question without obvious gaps.\n\n"
        "Mutually Exclusive: The themes must be conceptually distinct. There should not be significant ambiguity or overlap between them.\n\n"
        "Meaningful Granularity: The level of detail must be appropriate for a policy audience—not too broad and not too specific.\n"
        "</evaluation_criteria>\n"
        "<output_rules>\n\n"
        "Rule 1: If the thematic structure fully satisfies ALL evaluation criteria, your entire response MUST be the single word: None\n\n"
        "Rule 2: If the structure violates ANY of the criteria, you MUST provide a concise, bulleted list of the specific changes needed. "
        "Do not include a preamble or conclusion. Focus only on the edits.\n"
        "</output_rules>\n\n"
        "RESEARCH QUESTION:\n{rq}\n\n"
        "THEMES TO CRITIQUE:\n{themes}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_classify_concept_prompt() -> ChatPromptTemplate:
    """Prompt for classifying a single concept into one of the provided themes.

    Returns:
        ChatPromptTemplate: Template expecting variables: themes, concept
    """
    system = (
        "You are a Categorisation Engine. Your sole function is to match an input item "
        "to the single best category from a provided list. You are silent and precise, "
        "and only output the category number."
    )
    user = (
        "<role>\n"
        "You are a Categorisation Engine. Your sole function is to match an input item to the single best category from a provided list. "
        "You are silent, precise, and only output the category number.\n"
        "</role>\n"
        "<task>\n"
        "Analyse the provided CONCEPT and assign it to the single best-fitting theme from the numbered list of THEMES.\n"
        "</task>\n"
        "<methodology>\n\n"
        "Carefully read the full description of the CONCEPT.\n\n"
        "Review the name and description of every theme in the THEMES list.\n\n"
        "Identify the single theme that is the most logical and direct match for the concept.\n"
        "</methodology>\n"
        "<output_rules>\n\n"
        "Your entire response MUST be a single integer representing the theme number.\n\n"
        "Do NOT add any text, words, sentences, or punctuation.\n\n"
        "Example: If Theme 4 is the best fit, your response is 4.\n"
        "</output_rules>\n\n"
        "THEMES:\n{themes}\n\n"
        "CONCEPT:\n{concept}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_impact_summary_prompt() -> ChatPromptTemplate:
    """Prompt for writing a short impact summary for a theme.

    Returns:
        ChatPromptTemplate: Template expecting variables: name, sample
    """
    system = "You are a specialist in policy communication. Your expertise is distilling complex evidence into concise, clear, and impactful summaries for senior government officials."
    user = (
        "<role>\n"
        "You are a specialist in policy communication. Your expertise is distilling complex evidence into concise, clear, and impactful summaries for senior government officials.\n"
        "</role>\n"
        "<task>\n"
        "Write an evidence-based summary for the policy theme provided below. The summary must focus exclusively on the expected impacts and overall effectiveness of the interventions described in the representative concepts.\n"
        "</task>\n"
        "<constraints>\n\n"
        "Audience: The summary is for a senior UK policy advisor who needs to understand the key takeaway in under 30 seconds.\n\n"
        "Focus: Synthesise the outcomes and results from the concepts. Do not describe the concepts themselves, only their impact.\n\n"
        "Tone: The tone must be objective, formal, and confident.\n\n"
        "Word Count: Your response must be strictly between 35 and 45 words.\n\n"
        "Language: Use British English spelling and grammar.\n\n"
        "Evidence Grounding: Base your summary strictly on the provided theme and concepts. Do not add external information.\n"
        "</constraints>\n"
        "<output_format>\n"
        "Return a single paragraph of plain text only. Do not use markdown, headings, or bullet points.\n"
        "</output_format>\n\n"
        "THEME:\n{name}\n\n"
        "REPRESENTATIVE CONCEPTS:\n{sample}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


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
