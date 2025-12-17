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
    system = (
        "You are a Principal Private Secretary in the UK Civil Service. Your primary responsibility is to synthesise complex information into "
        "authoritative, concise, and politically neutral executive briefings for cabinet ministers."
    )
    user = (
        "<role>\n"
        "You are a Principal Private Secretary in the UK Civil Service. Your primary responsibility is to synthesise complex information into authoritative, concise, and politically neutral executive briefings for cabinet ministers.\n"
        "</role>\n"
        "<task>\n"
        "Synthesise the provided STRUCTURED DATA into a formal executive briefing that directly answers the user's RESEARCH QUESTION. The output must be highly structured and scannable.\n"
        "</task>\n"
        "<briefing_structure>\n"
        "Your briefing must follow this precise two-part structure:\n\n"
        "Begin with a single, declarative paragraph that directly answers the core of the user's research question based on the evidence, without restating or quoting the question.\n\n"
        "Follow the direct answer with a section that contains two distinct sub-headings in bold:\n\n"
        "Key Challenges: Under this heading, provide 2-3 concise bullet points outlining the primary problems or barriers identified in the evidence.\n\n"
        "Promising Interventions: Under this heading, provide 2-3 concise bullet points summarising the most effective solutions or policy levers.\n"
        "</briefing_structure>\n\n"
        "<constraints>\n\n"
        "Audience & Tone: The reader is a time-poor cabinet minister. The tone must be formal, objective, and confident.\n\n"
        "Evidence Grounding: Your briefing must be a direct synthesis of the provided STRUCTURED DATA only. Do not invent information or draw external conclusions.\n\n"
        "Conciseness: Each bullet point must be a single, clear, and impactful phrase or sentence. Avoid compound sentences.\n\n"
        "Directness: Do not restate or quote the research question in the output; provide the answer as a clear conclusion.\n\n"
        "Clarity: The distinction between Challenges and Interventions must be visually and substantively clear.\n"
        "</constraints>\n"
        "<output_format>\n"
        "Return a single block of text using markdown for formatting. The output must contain the Direct Answer sentence, followed by the Key Findings section with bolded sub-headings (Key Challenges and Promising Interventions) and bullet points (*). Do not include a title.\n"
        "</output_format>\n\n"
        "RESEARCH QUESTION:\n{rq}\n\n"
        "STRUCTURED DATA:\n{payload}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_outcome_themes_prompt() -> ChatPromptTemplate:
    """Prompt for discovering outcome themes from result/outcome concepts.

    This is a specialised version of the theme discovery prompt focused on
    clustering outcomes that are semantically similar (e.g., "obesity reduction",
    "lower BMI", "weight loss" → "Obesity Reduction").

    Returns:
        ChatPromptTemplate: Template expecting variables: rq, concepts
    """
    system = (
        "You are an expert in outcome clustering and meta-analysis. Your core skill is "
        "identifying when different outcome measures are conceptually measuring the same thing."
    )
    user = (
        "<role>\n"
        "You are an expert in outcome clustering and meta-analysis. Your core skill is "
        "identifying when different outcome measures are conceptually measuring the same thing.\n"
        "</role>\n"
        "<task>\n"
        "Analyse the provided OUTCOME CONCEPTS and group them into canonical outcome themes. "
        "Different studies may measure similar outcomes using different terminology or metrics. "
        "Your goal is to identify which outcomes are conceptually the same.\n"
        "</task>\n"
        "<examples>\n"
        "- 'BMI reduction', 'weight loss', 'lower body mass' → 'Weight/BMI Reduction'\n"
        "- 'reduced calorie intake', 'lower energy consumption', 'dietary improvement' → 'Caloric Intake'\n"
        "- 'increased physical activity', 'more exercise', 'higher step count' → 'Physical Activity Levels'\n"
        "</examples>\n"
        "<constraints>\n\n"
        "Semantic Equivalence: Group outcomes that measure conceptually the same thing, even if "
        "the specific metric or terminology differs.\n\n"
        "Canonical Naming: Use clear, standardised names for outcome themes (e.g., 'Obesity Prevalence' "
        "rather than 'people being less fat').\n\n"
        "Effect Direction Preservation: Do not conflate outcomes with opposite directions "
        "(e.g., 'weight gain' and 'weight loss' measure the same thing but in opposite directions).\n\n"
        "Evidence Grounding: Base themes only on the provided concepts.\n"
        "</constraints>\n"
        "<output_format>\n"
        'Return a single JSON object with a key "themes" containing a list of objects. '
        'Each object must have "theme_name" (canonical outcome name) and "theme_description" '
        "(brief explanation of what this outcome measures).\n"
        "</output_format>\n\n"
        "RESEARCH QUESTION:\n{rq}\n\n"
        "OUTCOME CONCEPTS:\n{concepts}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_impact_snapshot_prompt() -> ChatPromptTemplate:
    """Prompt for generating a quantitative impact snapshot for an intervention.

    Returns:
        ChatPromptTemplate: Template expecting variables: intervention_name, effect_data
    """
    system = (
        "You are a research synthesis specialist. Your expertise is distilling quantitative "
        "findings into concise, accurate impact statements."
    )
    user = (
        "<role>\n"
        "You are a research synthesis specialist. Your expertise is distilling quantitative "
        "findings into concise, accurate impact statements for policymakers.\n"
        "</role>\n"
        "<task>\n"
        "Generate a single-sentence impact snapshot summarising the quantitative effects "
        "of the intervention based on the provided effect data.\n"
        "</task>\n"
        "<examples>\n"
        "Good: '~2% reduction in obesity prevalence over 5 years'\n"
        "Good: '15-20% increase in fruit/vegetable consumption'\n"
        "Good: 'Mixed effects; 3 studies positive, 2 null'\n"
        "Bad: 'Studies show varying results on outcomes' (too vague)\n"
        "</examples>\n"
        "<constraints>\n\n"
        "Quantitative Focus: Include specific numbers, ranges, or effect sizes where available.\n\n"
        "Brevity: Maximum 15 words.\n\n"
        "Accuracy: Only state what the evidence supports. Use '~' for approximations.\n\n"
        "Uncertainty: If evidence is mixed or insufficient, say so clearly.\n"
        "</constraints>\n"
        "<output_format>\n"
        "Return a single sentence only. No markdown, no explanation.\n"
        "</output_format>\n\n"
        "INTERVENTION:\n{intervention_name}\n\n"
        "EFFECT DATA:\n{effect_data}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_enhanced_executive_briefing_prompt() -> ChatPromptTemplate:
    """Enhanced prompt for executive briefing with citations and structured evidence.

    This prompt produces briefings matching the ideal format with:
    - Core Answer & Directive
    - Evidence Coverage Snapshot
    - Key Interventions Table with citations
    - Actionable Takeaways
    - Top Citations for Review

    Returns:
        ChatPromptTemplate: Template expecting variables:
            research_question, evidence_coverage_json, interventions_json,
            issues_json, citation_mapping_json
    """
    system = (
        "You are a Principal Private Secretary in the UK Civil Service. Your primary responsibility "
        "is to synthesise complex research evidence into authoritative, citation-backed executive "
        "briefings for cabinet ministers. Every factual claim must be traceable to a source."
    )
    user = (
        "<role>\n"
        "You are a Principal Private Secretary in the UK Civil Service. Your primary responsibility "
        "is to synthesise complex research evidence into authoritative, citation-backed executive "
        "briefings for cabinet ministers.\n"
        "</role>\n\n"
        "<task>\n"
        "Synthesise the provided STRUCTURED DATA into a formal executive briefing that directly "
        "answers the RESEARCH QUESTION. The briefing must include inline citations using the "
        "provided citation keys.\n"
        "</task>\n\n"
        "<briefing_structure>\n"
        "Your briefing MUST follow this precise structure:\n\n"
        "## 1. Core Answer & Directive\n"
        "A single, authoritative paragraph (3-5 sentences) that:\n"
        "- Opens with a direct answer to the research question\n"
        "- Provides key qualifying context\n"
        "- Ends with a clear directive or recommendation\n"
        "- Includes 2-3 inline citations to key sources\n\n"
        "## 2. Evidence Base\n"
        "A brief snapshot (2-3 sentences) covering:\n"
        "- Total number of sources reviewed\n"
        "- Breakdown by study type (systematic reviews, RCTs, case studies)\n"
        "- Geographic coverage\n"
        "- Overall evidence strength assessment\n"
        "- Any notable gaps\n\n"
        "## 3. Key Interventions\n"
        "For the top 3-5 interventions, provide a markdown table with columns:\n"
        "| Intervention | Impact Snapshot | Evidence | Key Sources |\n"
        "Where:\n"
        "- Impact Snapshot: Quantitative summary (e.g., '~2% reduction over 5 years')\n"
        "- Evidence: Effect consensus (↑ positive, ↓ negative, ⟷ mixed)\n"
        "- Key Sources: 1-2 citation keys in brackets\n\n"
        "## 4. Key Challenges\n"
        "2-4 bullet points on barriers or issues, each with at least one citation.\n\n"
        "## 5. Actionable Takeaways\n"
        "2-3 bullet points with specific, implementable recommendations.\n\n"
        "## 6. Top Sources for Review\n"
        "List 3-5 key sources with their citation keys, titles, and brief relevance notes.\n"
        "</briefing_structure>\n\n"
        "<citation_rules>\n"
        "CRITICAL: You MUST use inline citations throughout the briefing.\n\n"
        "- Use citation keys exactly as provided (e.g., [Smith, 2023] or [Source 1])\n"
        "- Every factual claim about effects or findings MUST have a citation\n"
        "- Place citations immediately after the claim they support\n"
        "- Multiple sources can be cited together: [Smith, 2023; Jones, 2022]\n"
        "- If data is from your aggregated analysis, cite multiple supporting sources\n"
        "</citation_rules>\n\n"
        "<constraints>\n"
        "- Audience: Time-poor cabinet minister (5-minute read maximum)\n"
        "- Tone: Formal, objective, confident, politically neutral\n"
        "- Evidence Grounding: ONLY use information from the provided data\n"
        "- British English throughout\n"
        "- Do not restate the research question\n"
        "</constraints>\n\n"
        "<output_format>\n"
        "Return markdown text with the sections as H2 headings (##). Use tables, bullets, "
        "and bold text for scannability. Include a horizontal rule (---) between major sections.\n"
        "</output_format>\n\n"
        "---\n\n"
        "RESEARCH QUESTION:\n{research_question}\n\n"
        "---\n\n"
        "EVIDENCE COVERAGE:\n{evidence_coverage_json}\n\n"
        "---\n\n"
        "INTERVENTIONS:\n{interventions_json}\n\n"
        "---\n\n"
        "KEY ISSUES:\n{issues_json}\n\n"
        "---\n\n"
        "CITATION MAPPING:\n{citation_mapping_json}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


# =============================================================================
# RAG-GROUNDED STRUCTURED BRIEFING PROMPTS
# =============================================================================


def build_background_section_prompt() -> ChatPromptTemplate:
    """Prompt for generating the background/context section using RAG evidence.

    Returns:
        ChatPromptTemplate: Template expecting variables:
            research_question, issues_summary, evidence_context
    """
    system = (
        "You are a policy research analyst. Your task is to write a concise background "
        "section that contextualises a policy issue using evidence from retrieved documents."
    )
    user = (
        "<role>\n"
        "You are a policy research analyst writing for senior UK government officials.\n"
        "</role>\n\n"
        "<task>\n"
        "Write a background section (2-3 paragraphs) that contextualises the policy issue. "
        "Use the retrieved evidence excerpts to support your points with inline citations.\n"
        "</task>\n\n"
        "<key_issues>\n"
        "{issues_summary}\n"
        "</key_issues>\n\n"
        "<retrieved_evidence>\n"
        "{evidence_context}\n"
        "</retrieved_evidence>\n\n"
        "<citation_rules>\n"
        "ONLY cite evidence from the <retrieved_evidence> section using the exact [N] citation numbers provided.\n"
        "DO NOT cite sources not listed above. DO NOT invent citation numbers.\n"
        "Use format: [N] at the end of sentences, e.g., 'Studies show X [1].' or 'Y was found [2], [3].'\n"
        "Invalid formats: [1][3], [1,3], [1 and 3], (1), source [1]\n"
        "</citation_rules>\n\n"
        "<constraints>\n"
        "- Write 2-3 short paragraphs (150-250 words total)\n"
        "- Include inline citations [N] for claims from the evidence\n"
        "- Focus on the policy context, challenges, and why this matters\n"
        "- Do not introduce external information not in the evidence\n"
        "- British English\n"
        "</constraints>\n\n"
        "<output_format>\n"
        "Return plain paragraphs with [N] citations inline. No headings, no bullets.\n"
        "</output_format>\n\n"
        "RESEARCH QUESTION:\n{research_question}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_intervention_impact_prompt() -> ChatPromptTemplate:
    """Prompt for generating a RAG-grounded impact snapshot for an intervention.

    Returns:
        ChatPromptTemplate: Template expecting variables:
            intervention_name, effect_consensus, positive_count, negative_count,
            null_count, evidence_context
    """
    system = (
        "You are a research synthesis specialist. Your task is to write a concise "
        "impact statement grounded in specific evidence excerpts."
    )
    user = (
        "<role>\n"
        "You are a research synthesis specialist writing impact summaries for policymakers.\n"
        "</role>\n\n"
        "<task>\n"
        "Write a 2-3 sentence impact snapshot for the intervention below. "
        "Ground your statement in the retrieved evidence using [N] citations.\n"
        "</task>\n\n"
        "<intervention>\n"
        "Name: {intervention_name}\n"
        "Overall effect: {effect_consensus}\n"
        "Studies: {positive_count} positive, {negative_count} negative, {null_count} null\n"
        "</intervention>\n\n"
        "<retrieved_evidence>\n"
        "{evidence_context}\n"
        "</retrieved_evidence>\n\n"
        "<citation_rules>\n"
        "ONLY cite evidence from the <retrieved_evidence> section using the exact [N] citation numbers.\n"
        "DO NOT cite sources not listed above. DO NOT invent citation numbers.\n"
        "Valid: [1], [3] or [1], [2]\n"
        "Invalid: [1][3], [1,3], [1 and 3]\n"
        "</citation_rules>\n\n"
        "<constraints>\n"
        "- Maximum 3 sentences (50-80 words)\n"
        "- Include specific quantitative findings where available\n"
        "- Use [N] citations for specific claims\n"
        "- Format: **Impact:** [quantified effect with citation]. **Mechanism:** [explanation]\n"
        "</constraints>\n\n"
        "<output_format>\n"
        "Return a single statement with inline [N] citations. No markdown headers.\n"
        "</output_format>"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_recommendations_prompt() -> ChatPromptTemplate:
    """Prompt for generating RAG-grounded policy recommendations.

    Returns:
        ChatPromptTemplate: Template expecting variables:
            research_question, top_interventions, evidence_context
    """
    system = (
        "You are a senior policy advisor. Your task is to write actionable, "
        "evidence-based recommendations for government ministers. "
        "You will output structured JSON with exactly 3-4 recommendations."
    )
    user = (
        "<role>\n"
        "You are a senior policy advisor writing recommendations for UK cabinet ministers.\n"
        "</role>\n\n"
        "<task>\n"
        "Write exactly 3-4 policy recommendations based on the evidence below.\n"
        "</task>\n\n"
        "<top_interventions>\n"
        "{top_interventions}\n"
        "</top_interventions>\n\n"
        "<retrieved_evidence>\n"
        "{evidence_context}\n"
        "</retrieved_evidence>\n\n"
        "<citation_rules>\n"
        "ONLY cite evidence from the <retrieved_evidence> section using the exact [N] citation numbers provided.\n"
        "DO NOT cite sources not listed above. DO NOT invent citation numbers.\n"
        "Use comma/space delimited format: [1], [3] or [1], [2], [3]\n"
        "Invalid formats: [1][3], [1,3], [1 and 3], (1), source [1]\n"
        "</citation_rules>\n\n"
        "<requirements>\n"
        "For each recommendation provide:\n"
        "1. number: Sequential number (1, 2, 3, 4)\n"
        "2. title: Short action phrase of 3-6 words (e.g. 'Fund multicomponent school programmes')\n"
        "3. description: Detailed recommendation with specific evidence and [N] citations\n"
        "4. citation_numbers: List of integers for citations used (e.g. [3], [20], [7])\n\n"
        "Title examples:\n"
        "- 'Fund multicomponent school programmes'\n"
        "- 'Mandate behavioural components'\n"
        "- 'Prioritise whole-school approaches'\n"
        "- 'Expand parental engagement'\n"
        "</requirements>\n\n"
        "RESEARCH QUESTION:\n{research_question}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_impact_narrative_prompt() -> ChatPromptTemplate:
    """Prompt for generating a concise impact narrative for an intervention.

    Returns:
        ChatPromptTemplate: Template expecting variables:
            intervention_name, effect_consensus, evidence_context
    """
    system = (
        "You are a research analyst writing concise impact summaries for policymakers. "
        "Your summaries are specific, quantified where possible, and evidence-grounded."
    )
    user = (
        "<task>\n"
        "Write a 1-2 sentence impact summary for the intervention below. "
        "Include specific effect sizes, percentages, or outcomes where the evidence provides them. "
        "Use bold markdown for key metrics.\n"
        "</task>\n\n"
        "<intervention>\n"
        "{intervention_name}\n"
        "</intervention>\n\n"
        "<overall_effect>\n"
        "{effect_consensus}\n"
        "</overall_effect>\n\n"
        "<evidence>\n"
        "{evidence_context}\n"
        "</evidence>\n\n"
        "<citation_rules>\n"
        "ONLY cite evidence from the <evidence> section above using the exact [N] citation numbers provided.\n"
        "DO NOT cite sources not listed above. DO NOT invent citation numbers.\n"
        "Each citation number should appear at most once per sentence.\n"
        "Valid: [1], [3] or [1], [2], [3]\n"
        "Invalid: [1][3], [1,3], [1 and 3]\n"
        "</citation_rules>\n\n"
        "<requirements>\n"
        "- Maximum 2 sentences\n"
        "- Include at least one specific metric if available in evidence\n"
        "- Use **bold** for key numbers or effect sizes\n"
        "- Include [N] citation numbers from the evidence\n"
        "- Be direct: do not hedge or use phrases like 'the evidence suggests'\n"
        "</requirements>\n\n"
        "Write the impact summary:"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])


def build_core_answer_prompt() -> ChatPromptTemplate:
    """Prompt for generating the core answer at the top of the briefing.

    Returns:
        ChatPromptTemplate: Template expecting variables:
            research_question, top_interventions, intervention_count, background_context
    """
    system = (
        "You are a Principal Private Secretary. Your task is to write a headline "
        "answer that directly addresses a minister's research question."
    )
    user = (
        "<role>\n"
        "You are a Principal Private Secretary writing executive summaries for UK ministers.\n"
        "</role>\n\n"
        "<task>\n"
        "Write a headline answer (2-3 sentences) that directly addresses the research question. "
        "Follow it with a clear directive or key recommendation.\n"
        "</task>\n\n"
        "<context>\n"
        "Number of interventions reviewed: {intervention_count}\n"
        "Top interventions: {top_interventions}\n"
        "Background: {background_context}\n"
        "</context>\n\n"
        "<constraints>\n"
        "- Answer must be direct and authoritative (no hedging)\n"
        "- Maximum 3 sentences for the answer\n"
        "- Include a clear directive sentence\n"
        "- Do not restate the question\n"
        "</constraints>\n\n"
        "<output_format>\n"
        'Return JSON: {{"answer": "...", "directive": "..."}}\n'
        "</output_format>\n\n"
        "RESEARCH QUESTION:\n{research_question}"
    )
    return ChatPromptTemplate.from_messages([("system", system), ("user", user)])
