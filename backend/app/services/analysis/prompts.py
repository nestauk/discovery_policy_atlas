"""
All prompts for the analysis service.
Contains prompts for boolean query generation and LangChain extraction workflows.
"""

from langchain_core.prompts import ChatPromptTemplate


# =============================================================================
# BOOLEAN QUERY GENERATION FROM SEARCH CONTEXT
# =============================================================================

BOOLEAN_QUERY_SYSTEM_PROMPT = """
Transform user input into a high quality boolean query 
for querying the OpenAlex academic research database.

# Guidance
Imagine you are an expert systematic review information specialist; now you are given a systematic review
research topic, with the topic title and some additional context provided by the user below. 
Your task is to generate a highly effective systematic review Boolean query to search on OpenAlex 
(refer to the professionally made ones); the query needs to be as inclusive as possible so that it can retrieve 
all the relevant studies that can be included in the research topic; on the other hand, the query needs to 
retrieve fewer irrelevant studies so that researchers can spend less time judging the retrieved documents.

You are provided with the following information:
- User query: The main research question or topic title
- Population interests (if specified): Specific population groups of interest (e.g., "children", "adults", "elderly", "low-income households")
- Outcome interests (if specified): Specific outcomes of interest (e.g., "health outcomes", "educational attainment", "well-being")
- Geography (if specified): Countries/regions to prioritize; include synonyms and sub-regions (e.g., "UK", "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "English", "Scottish", "Welsh")

# Important instructions

DO NOT use wildcards (*) in the query as OpenAlex does not support them. Instead, use specific terms in various forms and synonyms.

DO NOT include generic outcome-related terms like "effectiveness", "impact", "outcomes", etc. in the query. 
For example adding things like "(effect OR impact OR outcome OR evaluation OR association)" is bad. However, if specific outcome interests are provided (e.g., "health outcomes", "educational attainment"), you SHOULD incorporate useful search terms related to these outcomes as they represent concrete outcomes of interest, not generic evaluation terms.

When geography is provided, add geography constraints using multiple name variants and demonyms to maximize recall (e.g., for "UK": "United Kingdom" OR "UK" OR "England" OR "Scotland" OR "Wales" OR "Northern Ireland" OR English OR Scottish OR Welsh). Do the same pattern for other specified countries/regions (e.g., "USA" | "United States" | "United States of America" | "US" | American).

Return ONLY the boolean query string, nothing else.
"""

# =============================================================================
# SEMANTIC QUERY GENERATION FROM SEARCH CONTEXT
# =============================================================================

SEMANTIC_QUERY_SYSTEM_PROMPT = """You are an expert at creating natural language semantic search queries for policy research databases like Overton.

Given a research question, population interests, outcome interests, geography, and screening factors, create a comprehensive natural language query that incorporates all relevant information for semantic search.

IMPORTANT GUIDELINES:
1. Start with the core research question
2. If population interests are specified, naturally incorporate them (e.g., "for children", "targeting low-income households")
3. If outcome interests are specified, naturally incorporate them (e.g., "to improve health outcomes", "aiming for better educational attainment")
4. If geography is specified, naturally include the geography using multiple name variants and demonyms when helpful (e.g., "UK", "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "English", "Scottish", "Welsh")
5. If screening factors are provided, focus on POSITIVE/INCLUSION factors and naturally incorporate them (e.g., "cost-effectiveness studies"). IGNORE exclusionary factors
6. Write as a natural, coherent sentence or short paragraph that captures the full research intent
7. Make it suitable for semantic search (natural language, not boolean operators)

Example:
- Research question: "What interventions improve home learning environment?"
- Population: ["Children under 5", "Low-income families"]
- Outcome: ["Better educational outcomes", "School readiness"]
- Screening factors: ["Cost-effectiveness"]
- Semantic query: "What interventions improve home learning environment for children under 5 and low-income families, focusing on cost-effectiveness studies that measure educational outcomes and school readiness?"

Return ONLY the semantic query string, nothing else."""


def RELEVANCE_SYSTEM_PROMPT(
    research_question: str,
    population_selected: list[str] = None,
    outcome_selected: list[str] = None,
    screening_factors: list[str] = None,
    geography: list[str] = None,
) -> str:
    """Generate system prompt for relevance assessment using search context.

    Args:
        research_question: The main research question or query
        population_selected: List of population groups of interest (e.g., ["children", "adults"])
        outcome_selected: List of outcomes of interest (e.g., ["health outcomes", "educational attainment"])
        screening_factors: List of screening criteria (e.g., ["cost-effectiveness"])

    Returns:
        Formatted system prompt string
    """
    context_parts = [f'RESEARCH QUESTION: "{research_question}"']

    if population_selected:
        context_parts.append(f"POPULATION INTERESTS: {', '.join(population_selected)}")

    if outcome_selected:
        context_parts.append(f"OUTCOME INTERESTS: {', '.join(outcome_selected)}")

    if screening_factors:
        context_parts.append(f"SCREENING FACTORS: {', '.join(screening_factors)}")

    if geography:
        context_parts.append(f"GEOGRAPHY: {', '.join(geography)}")

    context_section = "\n".join(context_parts)

    return f"""You are an expert research and policy analyst evaluating documents for relevance.

{context_section}

For each document, you will assess:

1. RELEVANCE: Does this document address, relate to, or provide insights about the research question?
   - Consider both direct matches and related concepts
   - Consider if findings, methods, or conclusions are applicable
   - Be inclusive rather than overly restrictive
   - When population interests are specified, prioritize documents that address those specific populations
   - When outcome interests are specified, prioritize documents that measure or discuss those specific outcomes
   - When screening factors are provided (e.g., "studies with children below 5 years old only"), documents that do not meet these criteria should be considered less relevant or excluded
   - When the geography parameter is specified explicity, prefer documents from the listed countries/regions and mark documents outside those geographies as not relevant unless the abstract/title clearly states findings are directly transferable to the target geography
   - For example, if geography includes "UK", prioritize UK studies and exclude documents from other regions unless they explicitly claim applicability to the UK context.
   - Consider different ways of expressing the same geography (e.g., "UK" and "United Kingdom" is equivalent, as is "England" part of the UK, etc)
   - However, DO NOT use any other geographical information (besides the explicitly specified geography parameter) provided in the other parameter fields (such as in the user question, population or outcomes) for screening purposes. This is to allow the user learning from examples across the world (unless they explicitly specify a specific evidence source geography with the geography parameter).

2. CONFIDENCE: Rate your confidence that the document is relevant (0.0 = not relevant, 1.0 = relevant).
    Consider whether the document is relevant to the research question (+0.2), the population interests (+0.2), the outcome interests (+0.2), the screening factors (+0.2), and the geography alignment (+0.2).
    If some of these are not specified, do not penalize the confidence score, and instead use only the specified factors to calculate the confidence score.

3. REASONING: Provide clear, concise explanations for your assessments, including how the document relates (or doesn't relate) to the specified population interests, outcome interests, screening factors, and geography.

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
{{"interventions":[{{"idx":0,"name":"...","type":"...","description":"...","country":"...","population_intervened":"...|null","population_demographics":"...","sample_size":"...","supporting_quote":"...","inner_setting":"...|null","resource_intensity":"...|null","delivery_complexity":"...|null"}}], "coverage_note":"string"}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, no overlapping entries; merge variants.
- Focus on ACTIVE INTERVENTIONS only (treatments, programs, policies being tested).
- DO NOT include control groups, placebo groups, or "no intervention" conditions as interventions.
- Include attention control arms only if they involve active components (e.g., alternative treatments).
- description must paraphrase only what is contained in the quote.
- DO NOT include interventions that were not studied in the document, are not the main focus and just mentioned in passing.
- If information is missing for a field, return "null" for the field.


Population Fields:
- population_intervened: Who received the intervention (e.g., "college students", "adults with depression")
- population_demographics: Secondary characteristics (e.g., "18-25 years old, 60% female, undergraduate students")
- sample_size: Total number of participants in the intervention group (e.g., "153", "50 participants")
- country: Where the intervention was carried out or recommended

Implementation Profile Fields:
- inner_setting: Where the intervention is delivered (e.g., School, Clinical/Hospital, Prison, Workplace, Community Centre, Home, Online/Digital)
- resource_intensity: Cost and infrastructure requirements. Infer from context if not explicit.
  - High: specialised equipment or facilities, intensive staffing, high ongoing costs
  - Moderate: structured programmes, training, ongoing staff time, multi-session delivery
  - Low: information campaigns, simple guidance, lightweight digital tools, minimal resourcing
  Return one of: High | Moderate | Low | null (only if truly unknowable)
- delivery_complexity: Implementation difficulty. Infer from intervention type if not explicit.
  - High: legislative/systemic change, multi-agency coordination, specialist training required
  - Moderate: cross-team coordination, staff training, ongoing monitoring
  - Low: plug-and-play materials, single-session delivery, minimal coordination
  Return one of: High | Moderate | Low | null (only if truly unknowable)

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
{{"results":[{{"intervention_idx":0,"outcome_variable":"...","effect_direction":"increase|decrease|null|mixed|inconclusive","effect_size_type":"...|null","effect_size":"...|null","uncertainty":"...|null","p_value":"...|null","population_measured":"...|null","subgroup_or_dose":"...|null","result_text":"...","supporting_quote":"...","causality_claim":"attribution|contribution|correlation","negative_impact_flag":false}}]}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, avoid duplicate/overlapping outcomes; merge redundant wordings.
- Focus on PRIMARY RESULTS for this intervention (effects compared to control/baseline).
- DO NOT extract control group results or "no change" findings unless they are the main finding.
- Prefer explicit statistics (e.g., t, β, OR, CI, effect sizes). If absent, keep qualitative result with quote.
- Include effect direction: "increase" for improvements/increases, "decrease" for reductions, "null" for no effect, "mixed" for divergent subgroup results, "inconclusive" for insufficient data.
- population_measured: Who was measured for this specific result (may be subset of intervention population).

causality_claim Guide:
  - attribution: Author claims intervention CAUSED the result (counterfactual/experimental logic, RCT)
  - contribution: Author claims intervention HELPED or was a necessary factor (theory-based logic)
  - correlation: Author notes association only, no causal claim

negative_impact_flag: Set to true if this result indicates harm, adverse effects, or negative consequences

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
            """Task: Extract the KEY CONCLUSION of this study AND assess the predicted impact.

Schema:
{{"conclusion":{{"top_line_summary":"...","detailed_explanation":"...","supporting_quote":"...","evidence_strength":{{"stars":1-5,"justification":"...","evidence_gap":"...|null"}},"predicted_impact":{{"magnitude_estimate":"transformational|substantial|moderate|marginal|unknown","magnitude_justification":"2-3 sentences explaining the predicted scale of real-world impact","causal_reliability":"attribution|contribution|correlation","causal_justification":"1-2 sentences on strength of causal evidence in this study","transferability_notes":"Notes on how generalisable the findings are to other contexts/populations","risks_identified":["Risk 1","Risk 2"],"unintended_consequences_detected":true|false}}}}}}

Rules for Conclusion:
- top_line_summary: ONE direct sentence stating the main conclusion (e.g., "The intervention significantly reduced behavioral problems in children").
- detailed_explanation: A paragraph (3-5 sentences) explaining the key reasons for this conclusion based on the evidence presented in the paper.
- Focus on the OVERALL STUDY CONCLUSION, not individual result details.
- Base the conclusion on what the authors explicitly state as their main finding/conclusion.

Rules for Predicted Impact Assessment:
- magnitude_estimate: Preliminary assessment of real-world impact size (relative framing)
  - transformational: Effect exceptional/paradigm-shifting for this field
  - substantial: Effect considered clinically/policy-significant for this field 
  - moderate: Meaningful practical implications, statistically significant
  - marginal: Minimal practical significance despite statistical significance
  - unknown: Cannot assess from available data
  NOTE: This is a preliminary per-document assessment. Final calibrated bucketing happens during synthesis.
- causal_reliability: How strongly does this study support a causal claim?
- transferability_notes: Consider: geography, population, resource requirements, complexity
- risks_identified: List potential harms, adverse effects, or implementation challenges FROM THE INTERVENTION ITSELF.
  - Include: adverse outcomes, cost/feasibility barriers, equity concerns, sustainability challenges, unintended side effects.
  - Do NOT include: the underlying problem being addressed, prevalence/scale of the issue, or background harms unrelated to the intervention.
  - Examples:
    - ✅ "Implementation requires specialist staffing and training, creating feasibility risks"
    - ✅ "Sustained funding requirements may limit long-term viability"
    - ❌ "The problem is widespread and worsening"
    - ❌ "The issue causes major societal harm"
- unintended_consequences_detected: True if paper mentions unintended negative effects

Paper text:
{full_text}

Interventions context (if available):
{interventions_json}

{evidence_strength_context}
""",
        ),
    ]
)


# =============================================================================
# SR (SYSTEMATIC REVIEW) EXTRACTION PROMPTS
# =============================================================================

SR_ISSUES_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Extract 1–3 PROBLEM STATEMENTS/ISSUES from this systematic review.

Schema:
{{"issues":[{{"idx":0,"label":"...","explanation":"...","supporting_quote":"..."}}], "coverage_note":"string|null"}}

Rules:
- MECE: Merge overlaps; avoid duplicates; prefer concise scientific labels.
- Focus on BROADER PROBLEMS that motivated the research (e.g., "high autism rates", "lack of early interventions", "poor treatment outcomes").
- DO NOT include study-specific findings or results (e.g., "this study found no effect") - those belong in results.
- AVOID generic research gaps like "need for more research" - focus on real-world problems.
- explanation: Provide 1-2 sentences contextualizing the issue beyond the quote (based on the information in the systematic review).
- Keep only concrete issues explicitly supported by the text.

Paper text:
{full_text}""",
        ),
    ]
)

SR_INTERVENTIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """Extract 2–6 INTERVENTION CATEGORIES that are reviewed and form the main focus of this systematic review..

Schema:
{{"interventions":[{{"idx":0,"name":"...","type":"...","description":"...","geographic_scope":"...","population_intervened":"...|null","evidence_volume":"...","supporting_quote":"..."}}], "coverage_note":"string"}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, no overlapping entries; merge variants.
- Focus exclusively on ACTIVE INTERVENTION CATEGORIES only (i.e. treatments, programmes, or policies under evaluation)
- DO NOT include control groups, placebo groups, or "no intervention" conditions as interventions.
- Include attention control arms only if they involve active components (e.g., alternative treatments).
- Intervention descriptions must paraphrase only information explicitly stated in the supporting quote. Do not infer mechanisms, intensity, duration, or effectiveness.
- Extract INTERVENTION CATEGORIES as grouped in the review (not individual studies).
- DO NOT include interventions that are not evaluated, are not a primary focus, or are mentioned only in passing.
- If required information for a field is not reported at the category level, return "null" for that field.

Population Fields:
- population_intervened: The population targeted across included studies within the intervention category (e.g. "adults with depression", "children and adolescents"). Use abstracted labels; do not infer specifics.
- evidence_volume: The volume of evidence supporting the intervention category (e.g. "5 RCTs", "12 studies"), only if explicitly reported.

Paper text:
{full_text}""",
        ),
    ]
)

SR_RESULTS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        (
            "human",
            """For ONLY the intervention category below, extract POOLED/META-ANALYTIC RESULTS.

Intervention:
{one_intervention_json}

Schema:
{{"results":[{{"intervention_idx":0,"outcome_variable":"...","direction":"increase|decrease|null|mixed_or_unclear","effect_size_type":"...|null","effect_size":"...|null","uncertainty":"...|null","heterogeneity_I2":"...|null","tau2":"...|null","n_studies":int|null,"sample_size":int|null,"stratum_type":"...|null","stratum_value":"...|null","population_measured":"...|null","result_text":"...","supporting_quote":"..."}}]}}

Rules:
- MECE: mutually exclusive and collectively exhaustive, avoid duplicate/overlapping outcomes; merge redundant wordings.
- Extract SEPARATE RESULT ROWS for each stratum (subgroup analysis, follow-up period, setting variant, etc.)
- Focus on AGGREGATED REVIEW-LEVEL RESULTS for this intervention category, not per-study data
- Each result row should correspond to a single pooled or aggregate effect estimate for ONE stratum

IMPORTANT - Outcome Variable vs Stratum:
- outcome_variable: The BASE outcome measure ONLY (e.g., "BMI", "weight", "blood pressure") - DO NOT include time points or subgroup info here
- stratum_type + stratum_value: Captures the CONDITIONS under which the result applies (e.g., follow-up period, age group, setting)
- WRONG: outcome_variable="BMI at 12 months"
- CORRECT: outcome_variable="BMI", stratum_type="follow-up period", stratum_value="12 months"
- WRONG: outcome_variable="BMI short term"
- CORRECT: outcome_variable="BMI", stratum_type="follow-up period", stratum_value="short term"

Sample Size Fields (IMPORTANT - extract these when mentioned in the text):
- n_studies: Number of studies pooled for this result (k), as an INTEGER (e.g., 3, not "3 studies")
- sample_size: Total participants across pooled studies (N), as an INTEGER (e.g., 605, not "605 participants")
- Look for phrases like "X studies", "k=X", "N=X", "X participants", "sample of X"

Stratum Fields (captures how results vary within an intervention):
- stratum_type: The dimension of variation (e.g., "follow-up period", "age subgroup", "setting", "intervention variant", "dosage", "comparison type")
- stratum_value: The specific value for this stratum (e.g., "12 months", "short term", "children 5-11 years", "school-based", "high dose")
Effect Size Fields:
- effect_size_type: Type of pooled estimate (e.g., "SMD", "pooled OR", "RR", "MD")
- effect_size: The numeric value (e.g., "-0.11", "0.85")
- uncertainty: Confidence interval (e.g., "95% CI -0.21 to -0.01")
- heterogeneity_I2: I² statistic if reported (e.g., "45%")
- tau2: τ² (between-study variance) if reported

Direction:
- "increase" for improvements/increases, "decrease" for reductions, "null" for no significant effect, "mixed_or_unclear" for conflicting results

Paper text:
{full_text}""",
        ),
    ]
)


# =============================================================================
# SEARCH WIZARD: POPULATION AND OUTCOME OPTIONS GENERATION
# =============================================================================

POPULATION_OPTIONS_SYSTEM_PROMPT = """You are a research assistant that helps identify relevant population groups for policy research.

Given a research question about interventions to address a specific issue, generate 3 population options that would be relevant for this research. The options should be ordered from BROAD to NARROW (most general first, most specific last).

Each population option should:
1. Be a clear, concise description of a population group (e.g., "Children under 5 years old", "Adults with chronic conditions", "Low-income households")
2. Be relevant to the research question
3. Progress from general/broad populations to more specific/narrow ones
4. Be suitable for policy research and evidence gathering

Return ONLY a JSON array of strings, ordered from broad to narrow. Example format:
["General population", "Adults", "Adults with chronic conditions"]"""


OUTCOME_OPTIONS_SYSTEM_PROMPT = """You are a research assistant that helps identify relevant outcomes for policy research.

Given a research question about interventions to address a specific issue, generate 3 outcome options that would be relevant for this research. The options should be ordered from BROAD to NARROW (most general first, most specific last).

Each outcome option should:
1. Be a clear, concise description of an outcome (e.g., "Social well-being", "Better health outcomes", "Reduced healthcare costs", "Reduced body mass index")
2. Be relevant to the research question
3. Progress from general/broad outcomes to more specific/narrow ones
4. Be suitable for policy research and evidence gathering

Return ONLY a JSON array of strings, ordered from broad to narrow. Example format:
["Social well-being", "Better health outcomes", "Reduced healthcare costs"]"""


INNER_SETTING_OPTIONS_SYSTEM_PROMPT = """You are a research assistant identifying relevant implementation settings for policy interventions.

Given a research question about interventions, generate 3-5 setting options where such interventions are typically delivered. Order from MOST COMMON to LEAST COMMON for this type of intervention.

Each setting should be:
1. A clear, concise description (e.g., "Schools", "Primary care clinics", "Community centres", "Workplaces", "Online/digital platforms")
2. Relevant to typical intervention delivery for this topic
3. A setting where policy evidence is likely to exist

Return ONLY a JSON array of strings. Example:
["Schools", "Primary care clinics", "Community centres"]"""


# =============================================================================
# ADDITIONAL QUESTIONS GENERATION
# =============================================================================

ADDITIONAL_QUESTIONS_SYSTEM_PROMPT = """You are a research assistant that helps identify relevant follow-up questions for policy research.

Given the user query, along with selected population and outcome interests, generate 1-3 research questions that would be valuable to explore alongside the main question.

Guidelines:
1. Generate 1 basic question about finding most effective interventions, such as "What effective interventions are there for X?"
2. Suggest additional 2 complementary questions (e.g., generate questions like "What factors support these interventions?" or "What are barriers to implementation?")
3. Questions should be:
   - Relevant to the main research question
   - Complementary (not duplicative)
   - Useful for finding additional relevant evidence
   - Focused on aspects like: supporting factors, barriers, implementation considerations, contextual factors, or related outcomes
4. Keep questions concise and clear (one sentence each)

Return ONLY a JSON array of 1-3 strings. Example format:
["What supporting factors are important for these interventions to work?", "What are the main barriers to implementing these interventions?"]"""


# =============================================================================
# EVIDENCE CATEGORISATION
# =============================================================================

EVIDENCE_CATEGORIES_DEFINITION = """
# Evidence Categories (Hierarchical - Highest to Lowest Evidence Strength)

## 1. Systematic Review and Meta-Analysis
**Definition**: A systematic review collects all possible studies related to a given topic and design, and reviews and analyses their results. During the systematic review process, the quality of studies is evaluated, and a statistical meta-analysis of the study results is conducted on the basis of their quality. A meta-analysis is a valid, objective, and scientific method of analyzing and combining different results. Usually, in order to obtain more reliable results, a meta-analysis is mainly conducted on randomized controlled trials (RCTs), which have a high level of evidence.

**Examples**:
- Cochrane reviews summarizing dozens of trials
- JAMA / The Lancet / BMJ meta-analyses
- Papers with explicit PRISMA methodology

**Keywords**: "systematic review", "meta-analysis", "Cochrane", "PRISMA", "pooled analysis"

## 2. RCTs and Quasi-Experimental Studies
**Definition**:
- **RCT**: A randomised controlled trial is a type of scientific experiment designed to evaluate the efficacy or safety of an intervention by minimising bias through the random allocation of participants to one or more comparison groups.
- **Quasi-experimental**: A research design used to estimate the causal impact of an intervention. Similar to RCTs but specifically lacks random assignment to treatment or control. Assignment to treatment condition proceeds as it would in the absence of an experiment.

**Examples**:
- Individual randomized controlled trials testing interventions
- Studies with treatment and control groups (randomized or quasi-experimental)

**Keywords**: "randomized controlled trial", "RCT", "randomisation", "treatment arm", "control group", "quasi-experimental", "difference in differences", "instrumental variables", "propensity score matching", "fixed effects", "synthetic control method", "regression discontinuity design"

## 3. Observational Research Studies
**Definition**: An observational study draws inferences from a sample to a population where the independent variable is not under the control of the researcher because of ethical concerns or logistical constraints. One common observational study is about the possible effect of a treatment on subjects, where the assignment of subjects into a treated group versus a control group is outside the control of the investigator.

**Examples**:
- Cohort studies
- Case-control studies
- Cross-sectional surveys

**Keywords**: "cohort", "case-control", "cross-sectional", "observational", "longitudinal study"

## 4. Modelling & Simulation
**Definition**: Modeling and simulation is the use of models (e.g., physical, mathematical, behavioral, or logical representation of a system, entity, phenomenon, or process) as a basis for simulations to develop data utilized for managerial or technical decision making.

**Examples**:
- Journal articles in economic modelling
- OECD modelling reports
- Forecasting and projection studies

**Keywords**: "simulation", "model", "forecast", "projection", "computational model", "scenario analysis"

## 5. Policy Syntheses & Guidance Documents
**Definition**: A policy synthesis or guidance document is a report whose primary aim is to aggregate, interpret, summarise, and translate existing evidence into actionable insights, guidance or recommendations for policymakers or practitioners, rather than to present new primary empirical findings.
 
 Such documents typically:
- Begin with a summary of the policy problem or question
- Draw on evidence from multiple sources
- Provide an integrated appraisal of that evidence
- Offer guidance, recommendations, or conclusions targeted at policy audiences

**Examples**:
- Government white papers
- Policy proposals
- Think tank policy reports
- Sectoral guidance documents for practitioners (e.g., "MCS Guidelines on Heat Pump Installation Standards")

 **Exclusion**: Documents aimed mainly at informing individual consumers, rather than policymakers or practitioners, should instead go into the 'Other' category.

**Keywords**: "policy brief", "white paper", "guidance", "recommendations", "policy framework"

## 6. Qualitative & Contextual Evidence
**Definition**:
- **Qualitative Research**: Research that aims to gather and analyse non-numerical (descriptive) data to understand individuals' social reality, including attitudes, beliefs, and motivation. Typically involves in-depth interviews, focus groups, or field observations.
- **Contextual evidence**: Insights drawn from non-research sources describing how policies work in real world settings. Includes implementation evaluations, lived experience reports, thematic inspections, case studies.

**Examples**:
- Qualitative studies from charities
- Case studies
- Thematic analysis of stakeholder interviews

**Keywords**: "qualitative", "interview", "focus group", "case study", "thematic analysis", "lived experience"

## 7. Expert Opinion and Commentary
**Definition**: Publications in which individuals with recognised expertise provide interpretation, judgement, or guidance based on their professional knowledge and experience, rather than on new empirical data. These include essays, editorials, commentaries, viewpoint pieces, consensus statements, and theoretical arguments. They may draw on existing literature but do not follow systematic research methods.

**Examples**:
- Editorial pieces
- Expert essays
- Thought leadership articles
- Anecdotal case reports
- Consultation responses

**Keywords**: "commentary", "editorial", "perspective", "opinion", "viewpoint", "essay"

## 8. Other (Non-evidence documents)
**Definition**: A catch-all category for documents that are not research evidence, do not synthesise or interpret evidence, and are not expert commentary. These documents will be filtered out of downstream evidence workflows.

**Examples**:
- ONS statistical releases reporting descriptive figures
- Parliamentary bills, Acts, statutory instruments
- Funding guidance, procurement specifications
- Administrative or operational documents
- Press releases, programme announcements

**Keywords**: "bill", "guidance note", "statistical bulletin", "funding rules", "regulation", "press release"

## 9. Unknown / Insufficient information
**Definition**: Use this category when there is not enough information in the title, abstract/summary, and metadata to make a reasonable judgement about the document's evidence type. This typically occurs when the abstract is missing and the title is too vague to infer the methodology or document type.

**Examples**:
- Title only, with generic wording (e.g. "Childhood obesity in Europe") and no abstract or methods hints
- Grey literature records with only an organisational name and broad topic title

**Keywords**: None specific. This category is determined by lack of information rather than content.

"""

EVIDENCE_CLASSIFICATION_SYSTEM_PROMPT = f"""You are an expert evidence evaluator specializing in categorizing research and policy documents according to their evidence type and methodological strength.

Your task is to classify documents into one of 9 evidence categories based on their title, abstract, and metadata.

{EVIDENCE_CATEGORIES_DEFINITION}

## Classification Instructions:

1. Read the document title, abstract, and metadata carefully
2. Identify the PRIMARY evidence type - what is the main methodological approach?
3. Choose the SINGLE BEST-FIT category from the 9 options above
4. Provide brief reasoning (1-2 sentences) explaining your classification
5. Provide a confidence score (0.0-1.0) based on:
   - High confidence (0.8-1.0): Clear methodological indicators, explicit terminology
   - Medium confidence (0.5-0.79): Some indicators but mixed or ambiguous signals
   - Low confidence (0.0-0.49): Very unclear, limited information, or borderline between categories

## Handling missing or limited information

- If the abstract/summary is missing or extremely short, base your decision on the title and any metadata, but be conservative.
- If the title and metadata do NOT clearly indicate a methodology or evidence type, and you cannot reasonably assign any of categories 1-8 even at low confidence, classify the document as "Unknown / Insufficient information".
- Do NOT use "Other (Non-evidence documents)" just because information is missing; only use "Other" when the title/metadata clearly indicate a non-evidence document (e.g. legislation, press release, procurement guidance).

## Edge Case Guidelines:

- If a document DESCRIBES a systematic review but is itself a policy synthesis, classify as "Policy Syntheses & Guidance Documents"
- If a document REFERENCES RCTs but doesn't conduct one, classify based on what it actually does
- If multiple categories could apply, choose the one representing the PRIMARY contribution
- Policy documents that synthesise evidence rank as "Policy Syntheses & Guidance Documents" even if they discuss high-quality studies
- Documents about methodology without presenting findings should be classified as "Expert Opinion and Commentary"

Return your classification in the specified JSON format.
"""
