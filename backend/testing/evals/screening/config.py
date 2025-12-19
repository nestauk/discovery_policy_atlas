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
]

# Combined list
ALL_EVAL_TARGETS = CSMED_TARGETS + SYNERGY_TARGETS + THREE_IE_TARGETS
