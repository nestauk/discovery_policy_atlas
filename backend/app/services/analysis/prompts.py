"""
All prompts for the analysis service.
Contains prompts for boolean query generation and LangChain extraction workflows.
"""

from langchain_core.prompts import ChatPromptTemplate


# =============================================================================
# BOOLEAN QUERY GENERATION
# =============================================================================

BOOLEAN_QUERY_SYSTEM_PROMPT = """You are an expert at creating boolean search queries for academic literature databases like OpenAlex and Overton.

Given a research question, create an optimized boolean search query that will find the most relevant academic papers. Follow these guidelines:

1. Use AND, OR, NOT operators appropriately
2. Group related terms with parentheses
3. Include synonyms and related terms with OR
4. Use quotes for exact phrases when appropriate
5. Consider academic terminology and jargon
6. Focus on terms that would appear in titles and abstracts
7. Keep the query concise while reasonably comprehensive; don't make it too complicated or too long
8. Consider policy-relevant terms and intervention types
9. Include both technical and common language terms

Return ONLY the boolean query string, nothing else."""


# =============================================================================
# RELEVANCE AND DOCUMENT TYPE CLASSIFICATION
# =============================================================================


def RELEVANCE_SYSTEM_PROMPT(query: str) -> str:
    """Generate system prompt for relevance and document type assessment."""
    return f"""You are an expert research and policy analyst evaluating documents for relevance and classification.

QUERY: "{query}"

For each document, you will assess:

1. RELEVANCE: Does this document address, relate to, or provide insights about the query topic?
   - Consider both direct matches and related concepts
   - Consider if findings, methods, or conclusions are applicable
   - Be inclusive rather than overly restrictive

2. DOCUMENT TYPE CLASSIFICATION:
   - **research_paper**: Empirical studies, experiments, clinical trials, data analyses
   - **reviews**: Reviews, meta-analyses, systematic reviews, and other literature reviews
   - **policy_document**: Policy recommendations, guidelines, frameworks, position papers, government reports, policy briefs, regulatory documents
   - **other**: News articles, announcements, transcripts, opinion pieces, editorials, non-peer reviewed content

3. CONFIDENCE: Rate your confidence in the relevance assessment (0.0 = uncertain, 1.0 = very confident)

4. REASONING: Provide clear, concise explanations for your assessments.

Base your evaluation primarily on the title and abstract/summary provided. Be thorough but concise in your reasoning."""


# =============================================================================
# LANGCHAIN EXTRACTION WORKFLOWS
# =============================================================================

# Universal system prompt used for all extraction stages
EXTRACTION_SYSTEM_PROMPT = """You extract ONLY verbatim, well-grounded information from the provided paper.
Return STRICT JSON matching the schema. No explanations.

CRITICAL: Every supporting_quote MUST be copied EXACTLY as it appears in the paper - word for word, punctuation for punctuation. Do NOT paraphrase, summarize, or rephrase. Copy the exact text.

Every item MUST include a supporting_quote copied verbatim from the paper.
If a field cannot be grounded with a quote, omit the item.
Apply the MECE principle within each list you produce: items must be mutually exclusive (no overlaps) and collectively exhaustive for the content explicitly discussed in the paper. If true collective exhaustiveness is not possible, include a short coverage_note at the end explaining any gaps."""


# Stage A: Issues extraction
ISSUES_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Task: Extract 1–3 key PROBLEM STATEMENTS/ISSUES that motivated this research.

Schema:
{{"issues":[{{"idx":0,"label":"...","explanation":"...","supporting_quote":"..."}}], "coverage_note":"string|null"}}

Rules:
- MECE: Merge overlaps; avoid duplicates; prefer concise scientific labels.
- Focus on BROADER PROBLEMS that motivated the research (e.g., "high autism rates", "lack of early interventions", "poor treatment outcomes").
- DO NOT include study-specific findings or results (e.g., "this study found no effect") - those belong in results.
- AVOID generic research gaps like "need for more research" - focus on real-world problems.
- explanation: Provide 1-2 sentences contextualizing the issue beyond the quote (based on the information in the paper).
- Keep only concrete issues explicitly supported by the text.

Paper text:
{full_text}""",
        ),
    ]
)


# Stage B: Interventions extraction
INTERVENTIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Task: Extract 2–6 ACTIVE INTERVENTIONS/PROGRAMS evaluated or proposed, that are the main focus of the study.

Schema:
{{"interventions":[{{"idx":0,"name":"...","type":"...","description":"...","study_type":"...","country":"...","population_intervened":"...|null","population_demographics":"...","sample_size":"...","supporting_quote":"..."}}], "coverage_note":"string"}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, no overlapping entries; merge variants.
- Focus on ACTIVE INTERVENTIONS only (treatments, programs, policies being tested).
- DO NOT include control groups, placebo groups, or "no intervention" conditions as interventions.
- Include attention control arms only if they involve active components (e.g., alternative treatments).
- description must paraphrase only what is contained in the quote.
- DO NOT include interventions that were not studied in the document, are not the main focus and just mentioned in passing.
- If information is missing for a field, return "null" for the field.

Study Type (Maryland Scientific Methods Scale - indicate only the letter):
   a) purely cross-sectional study
   b) Study measures outcome pre and post
   c) purely cross-sectional study, uses control variables
   d) Study measures outcome pre and post
   e) Comparison of outcomes in treated group
   f) Quasi-experimental study
   g) Randomised controlled trial
   h) Meta-analysis
   i) Not a trial, but rather a policy recommendation paper or a theoretical modelling study
   j) Not a scientific study, but a news article, opinion piece or government announcement

Population Fields:
- population_intervened: Who received the intervention (e.g., "college students", "adults with depression")
- population_demographics: Secondary characteristics (e.g., "18-25 years old, 60% female, undergraduate students")
- sample_size: Total number of participants in the intervention group (e.g., "153", "50 participants")
- country: Where the intervention was carried out or recommended

Paper text:
{full_text}""",
        ),
    ]
)


# Stage C: Mapping (issues ↔ interventions)
MAPPING_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Task: Link issues to the interventions used to address them. Provide a grounded rationale.

Inputs:
Issues JSON: {issues_json}
Interventions JSON: {interventions_json}

Schema:
{{"mappings":[{{"issue_idx":0,"intervention_idx":0,"rationale":"...","supporting_quote":"..."}}]}}

Paper text:
{full_text}""",
        ),
    ]
)


# Stage D: Results (per intervention)
RESULTS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Task: For ONLY the intervention below, extract 1–5 MECE RESULTS showing the intervention's effects.

Intervention:
{one_intervention_json}

Schema:
{{"results":[{{"intervention_idx":0,"outcome_variable":"...","effect_direction":"increase|decrease|null","effect_size_type":"...|null","effect_size":"...|null","uncertainty":"...|null","p_value":"...|null","population_measured":"...|null","subgroup_or_dose":"...|null","result_text":"...","supporting_quote":"..."}}]}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, avoid duplicate/overlapping outcomes; merge redundant wordings.
- Focus on PRIMARY RESULTS for this intervention (effects compared to control/baseline).
- DO NOT extract control group results or "no change" findings unless they are the main finding.
- Prefer explicit statistics (e.g., t, β, OR, CI, effect sizes). If absent, keep qualitative result with quote.
- Include effect direction: "increase" for improvements/increases, "decrease" for reductions, "null" for no effect.
- population_measured: Who was measured for this specific result (may be subset of intervention population).

Paper text:
{full_text}""",
        ),
    ]
)


# Stage E: Conclusions extraction
CONCLUSIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Task: Extract the KEY CONCLUSION of this study based on the research findings.

Schema:
{{"conclusion":{{"top_line_summary":"...","detailed_explanation":"...","supporting_quote":"..."}}}}

Rules:
- top_line_summary: ONE direct sentence stating the main conclusion (e.g., "The intervention significantly reduced behavioral problems in children").
- detailed_explanation: A paragraph (3-5 sentences) explaining the key reasons for this conclusion based on the evidence presented in the paper.
- Focus on the OVERALL STUDY CONCLUSION, not individual result details.
- Base the conclusion on what the authors explicitly state as their main finding/conclusion.
- The detailed explanation should synthesize the key evidence that supports the top-line conclusion.

Paper text:
{full_text}""",
        ),
    ]
)
