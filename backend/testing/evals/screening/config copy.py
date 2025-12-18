# scripts/evals/screening/config.py

# ==========================================
# 1. ACADEMIC BASELINE: CSMeD (Cochrane)
# Source: CSMeD-FT-dev.csv
# ==========================================
CSMED_TARGETS = [
    {
        "id": "CD010254",
        "name": "Clinical_Rosuvastatin",
        "query": "Assess the effects of various doses of rosuvastatin on serum total cholesterol and LDL-cholesterol in participants with and without cardiovascular disease.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD010901",
        "name": "Policy_DrugOffenders",
        "query": "Effectiveness of interventions for drug-using offenders with co-occurring mental health problems in reducing criminal activity or drug use.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD011737",
        "name": "PublicHealth_SaturatedFat",
        "query": "Effect of reducing saturated fat intake and replacing it with carbohydrate, polyunsaturated or monounsaturated fat on mortality and cardiovascular morbidity.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD007228",
        "name": "Systems_TelemonitoringHF",
        "query": "Structured telephone support or non-invasive home telemonitoring compared to standard practice for people with heart failure.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD005563",
        "name": "Hospital_DeliriumPrevention",
        "query": "Effectiveness of interventions for preventing delirium in hospitalised non-Intensive Care Unit (non-ICU) patients.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD010534",
        "name": "Family_ParentInfantPsych",
        "query": "Effectiveness of parent-infant psychotherapy (PIP) in improving parental and infant mental health and the parent-infant relationship.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD001191",
        "name": "Aging_AlzheimersDrug",
        "query": "Clinical efficacy and safety of rivastigmine for patients with dementia of Alzheimer's type.",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD007714",
        "name": "Respiratory_NIV_COPD",
        "query": "Does adding non-invasive ventilation during pulmonary rehabilitation enable people with COPD to exercise at higher intensities and improve health-related quality of life compared with exercise training alone?",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD006612",
        "name": "Cardio_Homocysteine",
        "query": "Do homocysteine-lowering therapies (folate, vitamin B12, vitamin B6 or combination therapy) reduce cardiovascular events compared with placebo or usual care in high-risk adults?",
        "dataset_source": "CSMeD",
    },
    {
        "id": "CD008729",
        "name": "Psych_OncologySupport",
        "query": "Which psychological interventions reduce distress and improve coping or quality of life for women with non-metastatic breast cancer during or after active treatment?",
        "dataset_source": "CSMeD",
    },
]

# ==========================================
# 2. DOMAIN EXTENSION: SYNERGY (Open Science)
# Source: Individual CSVs from index.json
# ==========================================
SYNERGY_TARGETS = [
    # --- Psychology & Mental Health ---
    {
        "id": "van_Dis_2020",
        "name": "Psych_CBT_Anxiety",
        "query": "What are the long-term outcomes of Cognitive Behavioral Therapy (CBT) for anxiety-related disorders?",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "van_de_Schoot_2018",
        "name": "Psych_PTSD_Trajectories",
        "query": "Studies identifying or reporting on latent trajectories of PTSD symptoms in diverse populations.",
        "dataset_source": "SYNERGY",
    },
    # --- Computer Science & Engineering (Non-Medical) ---
    {
        "id": "Hall_2012",
        "name": "CS_FaultPrediction",
        "query": "Predicting faults in software units using code metrics and models: a systematic review of performance.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "Radjenovic_2013",
        "name": "CS_SoftwareMetrics",
        "query": "Software fault prediction metrics and systematic literature reviews in software engineering.",
        "dataset_source": "SYNERGY",
    },
    # --- Clinical & Rare Disease ---
    {
        "id": "Appenzeller-Herzog_2019",
        "name": "Clinical_WilsonDisease",
        "query": "Comparative effectiveness of common therapies (e.g., chelators, zinc) for Wilson disease.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "Bos_2018",
        "name": "Clinical_SmallVesselDisease",
        "query": "Association between cerebral small vessel disease (CSVD) structures and the risk of dementia or cognitive decline.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "Wolters_2018",
        "name": "Clinical_HeartBrain",
        "query": "Association between coronary heart disease or heart failure and the subsequent risk of dementia or cognitive impairment.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "Oud_2018",
        "name": "Psych_BPD_Therapies",
        "query": "Effectiveness of psychotherapies such as schema-focused, mentalization-based, dialectical behaviour or supportive therapy for adults diagnosed with borderline personality disorder.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "van_der_Valk_2021",
        "name": "Endocrine_StressBiomarkers",
        "query": "Associations between hypothalamic–pituitary–adrenal axis biomarkers (e.g., cortisol, copeptin, hair cortisol) and metabolic or psychiatric outcomes in adult humans.",
        "dataset_source": "SYNERGY",
    },
    {
        "id": "van_der_Waal_2022",
        "name": "Oncology_SharedDecisions",
        "query": "Barriers, facilitators and digital supports influencing shared decision-making, treatment preferences and clinician–patient communication for people with cancer.",
        "dataset_source": "SYNERGY",
    },
]

# ==========================================
# 3. GLOBAL DEVELOPMENT: 3ie Evidence Gap Maps
# Source: Exported CSVs from 3ie Evidence Hub
# ==========================================
THREE_IE_TARGETS = [
    # --- 1. Climate & Environment ---
    {
        "id": "3ie_EGM_Climate_2024",
        "name": "Enviro_ClimateBiodiversity",
        "query": "What are the effects of climate change and biodiversity interventions on environmental and human wellbeing outcomes?",
        "dataset_source": "3ie",
    },
    # --- 2. Governance & Democracy ---
    {
        "id": "3ie_EGM_Governance_2023",
        "name": "Gov_GoodGovernance",
        "query": "Interventions to strengthen governance effectiveness, rule of law, and accountability in low- and middle-income countries.",
        "dataset_source": "3ie",
    },
    # --- 3. Migration ---
    {
        "id": "3ie_EGM_Migration_2023",
        "name": "Policy_IrregularMigration",
        "query": "Interventions that address the root causes and drivers of irregular migration, such as economic opportunities and conflict resilience.",
        "dataset_source": "3ie",
    },
    # --- 4. Food Security ---
    {
        "id": "3ie_EGM_FoodSystems_2024",
        "name": "Agri_FoodSystems",
        "query": "Effects of food systems interventions (production, supply chain, food environment) on food security and nutrition outcomes.",
        "dataset_source": "3ie",
    },
    # --- 5. Gender & Health Rights ---
    {
        "id": "3ie_EGM_SRHR_2024",
        "name": "Health_SexualReproRights",
        "query": "Impact of interventions to promote sexual and reproductive health and rights (SRHR) and women's empowerment.",
        "dataset_source": "3ie",
    },
    # --- 6. Infrastructure & WASH ---
    {
        "id": "3ie_EGM_WASH_2023",
        "name": "Infra_WaterSanitation",
        "query": "What is the association between WASH interventions (water access, sanitation facilities) and development outcomes like health and prosperity?",
        "dataset_source": "3ie",
    },
    # --- 7. Public Health & Nutrition ---
    {
        "id": "3ie_EGM_Anaemia_2024",
        "name": "Health_AnaemiaReduction",
        # Map: Interventions to reduce anaemia in low- and middle-income countries
        "query": "Effectiveness of interventions to reduce anaemia (fortification, supplementation, disease control) in low- and middle-income countries.",
        "dataset_source": "3ie",
    },
    # --- 8. Energy & Infrastructure ---
    {
        "id": "3ie_EGM_Energy_2024",
        "name": "Infra_SustainableEnergy",
        # Map: Promoting Sustainable Energy Development
        "query": "Impact of interventions to promote sustainable energy access, renewables, and efficient technologies in developing countries.",
        "dataset_source": "3ie",
    },
    # --- 9. Conservation & Land Use ---
    {
        "id": "3ie_EGM_LandUse_2024",
        "name": "Enviro_LandUseForestry",
        # Map: Land-use change and forestry programmes
        "query": "Effects of land-use change and forestry programmes (conservation, restoration, management) on environmental and socio-economic outcomes.",
        "dataset_source": "3ie",
    },
    # --- 10. Humanitarian & Disaster ---
    {
        "id": "3ie_EGM_Resilience_2023",
        "name": "Social_ResilienceShocks",
        # Map: Strengthening resilience against shocks and stressors
        "query": "Interventions to strengthen resilience against covariate shocks, stressors, and recurring crises in low- and middle-income countries.",
        "dataset_source": "3ie",
    },
]

# Combined list
ALL_EVAL_TARGETS = CSMED_TARGETS + SYNERGY_TARGETS + THREE_IE_TARGETS
