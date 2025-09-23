"""
All prompts for the analysis service.
Contains prompts for boolean query generation and LangChain extraction workflows.
"""

from langchain_core.prompts import ChatPromptTemplate


# =============================================================================
# BOOLEAN QUERY GENERATION
# =============================================================================

BOOLEAN_QUERY_SYSTEM_PROMPT = """You are an expert at creating boolean search queries for academic literature databases like OpenAlex and Overton.

Given a research question, extract the key concepts and create a targeted boolean search query. DO NOT use the entire research question as a search term.

IMPORTANT: Break down the research question into its core components and search terms. For example:
- Research question: "What is the biggest interventions for decarbonising home heating?"
- Key concepts: decarbonisation, home heating, interventions, residential heating, carbon reduction
- Boolean query: (decarbonis OR "carbon reduction" OR "emissions reduction") AND ("home heating" OR "residential heating" OR "domestic heating") AND (intervention* OR program* OR policy OR measure*)

For policy-specific queries, focus on the underlying research topics rather than specific policy names:
- Research question: "Which UK home-heating incentives have reduced gas?"
- Key concepts: heating policy evaluation, residential gas consumption, energy efficiency programs
- Boolean query: ("residential heating" OR "home heating" OR "domestic heating") AND ("gas consumption" OR "natural gas" OR "gas demand") AND (policy OR program* OR incentive* OR intervention*) AND (reduc* OR efficiency OR savings)

For queries with multiple sub-questions, use OR to connect the concepts and terms of each sub-question.
- Research question: "What is the biggest interventions for decarbonising home heating? And what is the biggest interventions for decarbonising transport?"
- Key concepts: decarbonisation, home heating, transport, interventions, residential heating, carbon reduction
- Boolean query: ((decarbonis OR "carbon reduction" OR "emissions reduction") AND (("home heating" OR "residential heating" OR "domestic heating") OR ("transport" OR "vehicle" OR "electricity" OR "hybrid" OR "fuel cell")) AND (intervention* OR program* OR policy* OR measure*))

Guidelines:
1. Extract 2-4 main concepts from the research question
2. Use AND to connect different concepts that all should be present in the documents
3. Use OR to include synonyms and related terms within each concept, or alternative concepts that expand the search scope
4. You can use nested parentheses to group concepts and terms that should be treated as a single concept or term, and then use OR to connect the groups of concepts
5. Use wildcards (*) for word variations (e.g., intervention*)
6. Use quotes for exact phrases when beneficial
7. Include both technical and common language terms
8. Focus on terms that would realistically appear in academic paper titles and abstracts
9. For policy queries, focus on research about the underlying phenomena rather than specific policy names
10. Consider broader academic terminology (evaluation, effectiveness, impact, outcomes)
11. Prioritize nouns and key descriptive terms over question words (what, how, why)
12. Include related research terms like "evaluation", "impact", "effectiveness" for policy questions

Most importantly, keep the query sufficiently general so that we get more results, but roughly in the right ballpark.

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
            """Task: Extract the KEY CONCLUSION of this study AND assess the evidence strength and predicted impact.

Schema:
{{"conclusion":{{"top_line_summary":"...","detailed_explanation":"...","supporting_quote":"...","evidence_strength":{{"stars":1-5,"justification":"...","evidence_gap":"...|null"}},"predicted_impact":{{"stars":1-5,"justification":"...","evidence_gap":"...|null"}}}}}}

Rules for Conclusion:
- top_line_summary: ONE direct sentence stating the main conclusion (e.g., "The intervention significantly reduced behavioral problems in children").
- detailed_explanation: A paragraph (3-5 sentences) explaining the key reasons for this conclusion based on the evidence presented in the paper.
- Focus on the OVERALL STUDY CONCLUSION, not individual result details.
- Base the conclusion on what the authors explicitly state as their main finding/conclusion.

Rules for Evidence Strength Assessment (methodological quality, reliability, robustness):
- ⭐⭐⭐⭐⭐ (5): RCT or strong quasi-experimental, large sample, validated measures, sufficient mitigation of confounders, strong statistical significance, large effect size.
- ⭐⭐⭐⭐ (4): RCT/quasi, moderate/large sample, partial mitigation of confounders, validated methods, medium or smaller effect sizes.
- ⭐⭐⭐ (3): RCT/quasi with moderate sample, partial mitigation, methods not fully validated; or small sample but some strong controls.
- ⭐⭐ (2): Weak quasi-experimental or small RCT, limited controls, unvalidated methods, limited statistical power.
- ⭐ (1): Anecdotal evidence, uncontrolled pre–post, insufficient mitigation, small/biased sample, no statistical significance despite correlation.

Rules for Predicted Impact Assessment (likelihood of scaling outcomes beyond study context):
- ⭐⭐⭐⭐⭐ (5): Strong causal evidence, large effects, replicated or validated, generalisable to population, mitigation of confounders, strong evidence of external validity.
- ⭐⭐⭐⭐ (4): Adequate causal link, medium effect size, good but partial mitigation, some generalisability concerns, but broadly reliable.
- ⭐⭐⭐ (3): Smaller effect size or more context-limited, moderate sample, some threats to generalisability, still a plausible impact.
- ⭐⭐ (2): Uncertain or inconsistent evidence, weak causal link, effects fragile or highly context-specific.
- ⭐ (1): Anecdotal or speculative impact only, with minimal empirical support.

Assessment Rules:
- Begin at 5 stars and discount by 1 for each unmet major criterion (down to 1).
- If evidence is insufficient for assessment, set "stars": null and add "evidence_gap" explanation.
- Focus on the MAIN intervention studied in the paper, not secondary or control conditions.
- justification: 2-4 sentences explaining rating and discounting logic based on aggregate assessment of the study's evidence.

Paper text:
{full_text}

Interventions context (if available):
{interventions_json}""",
        ),
    ]
)
