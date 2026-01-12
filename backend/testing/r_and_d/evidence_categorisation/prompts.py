"""
Prompts for evidence categorization
"""

EVIDENCE_CATEGORIES_DEFINITION = """
# Evidence Categories (Hierarchical - Highest to Lowest Evidence Strength)

## 1. Systematic Review and Meta-Analysis
**Definition**: A systematic review collects all possible studies related to a given topic and design, and reviews and analyses their results. During the systematic review process, the quality of studies is evaluated, and a statistical meta-analysis of the study results is conducted on the basis of their quality. A meta-analysis is a valid, objective, and scientific method of analyzing and combining different results. Usually, in order to obtain more reliable results, a meta-analysis is mainly conducted on randomized controlled trials (RCTs), which have a high level of evidence.

**Examples**:
- Cochrane reviews summarizing dozens of trials
- Systematic reviews from Blueprint
- Papers with explicit PRISMA methodology

**Keywords**: "systematic review", "meta-analysis", "Cochrane", "PRISMA", "pooled analysis"

## 2. RCTs and Quasi-Experimental Studies
**Definition**:
- **RCT**: A randomised controlled trial is a type of scientific experiment designed to evaluate the efficacy or safety of an intervention by minimising bias through the random allocation of participants to one or more comparison groups.
- **Quasi-experimental**: A research design used to estimate the causal impact of an intervention. Similar to RCTs but specifically lacks random assignment to treatment or control. Assignment to treatment condition proceeds as it would in the absence of an experiment.

**Examples**:
- Individual randomized controlled trials testing interventions
- Studies with treatment and control groups (randomized or quasi-experimental)

**Keywords**: "randomized controlled trial", "RCT", "randomisation", "treatment arm", "control group", "quasi-experimental",  "difference in differences", "instrumental variables", "propensity score matching", "fixed effects", "synthetic control method", "regression discontinuity design"

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
**Definition**: A policy synthesis or guidance document is a report whose primary aim is to aggregate, interpret, summarise, and translate existing evidence into actionable insights, guidance or recommendations for policymakers or practitioners, rather than to present new primary empirical findings. Documents aimed mainly at informing individual consumers, rather than policymakers or practitioners, should be treated as low-rigour contextual material rather than evidence. Such documents typically:
- Begin with a summary of the policy problem or question
- Draw on evidence from multiple sources
- Provide an integrated appraisal of that evidence
- Offer guidance, recommendations, or conclusions targeted at policy audiences

**Examples**:
- Government white papers
- Policy proposals
- Think tank policy reports
- Sectoral guidance documents for practitioners (e.g., “MCS Guidelines on Heat Pump Installation Standards”)

**Keywords**: "policy brief", "white paper", "guidance", "recommendations", "policy framework"

## 6. Qualitative & Contextual Evidence
**Definition**:
- **Qualitative Research**: Research that aims to gather and analyse non-numerical (descriptive) data to understand individuals' social reality, including attitudes, beliefs, and motivation. Typically involves in-depth interviews, focus groups, or field observations.
- **Contextual evidence**: Insights drawn from non-research sources describing how policies work in real world settings. Includes implementation evaluations, lived experience reports, thematic inspections, case studies.

**Examples**:
- Qualitative studies from charities
- Case studies
- Parliamentary commission evidence synthesis

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
**Definition**: Use this category when there is not enough information in the title, abstract/summary, and metadata to make a reasonable judgement about the document’s evidence type. This typically occurs when the abstract is missing and the title is too vague to infer the methodology or document type.

**Examples**:
- Title only, with generic wording (e.g. "Childhood obesity in Europe") and no abstract or methods hints
- Grey literature records with only an organisational name and broad topic title

**Keywords**: None specific. This category is determined by lack of information rather than content.

"""

CLASSIFICATION_SYSTEM_PROMPT = f"""You are an expert evidence evaluator specializing in categorizing research and policy documents according to their evidence type and methodological strength.

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
- If the title and metadata do NOT clearly indicate a methodology or evidence type, and you cannot reasonably assign any of categories 1–8 even at low confidence, classify the document as "Unknown / Insufficient information".
- Do NOT use "Other (Non-evidence documents)" just because information is missing; only use "Other" when the title/metadata clearly indicate a non-evidence document (e.g. legislation, press release, procurement guidance).

## Edge Case Guidelines:

- If a document DESCRIBES a systematic review but is itself a policy synthesis, classify as "Policy Syntheses & Guidance Documents"
- If a document REFERENCES RCTs but doesn't conduct one, classify based on what it actually does
- If multiple categories could apply, choose the one representing the PRIMARY contribution
- Policy documents that synthesise evidence rank as "Policy Syntheses & Guidance Documents" even if they discuss high-quality studies
- Documents about methodology without presenting findings should be classified as "Expert Opinion and Commentary"

Return your classification in the specified JSON format.
"""

CLASSIFICATION_USER_PROMPT = """Classify the following document:

**Title**: {title}

**Abstract/Summary**: {abstract}

**Metadata**:
- Source: {source}
- Type: {doc_type}
- Year: {year}

Provide your classification following the system instructions.
"""
