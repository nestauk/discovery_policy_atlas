"""
Model configuration for agentic briefing.

Defines which LLM models are used for each component of the
tool-augmented briefing pipeline.
"""

# Orchestrator - decides which tools to call and how to use results
# Uses gpt-5.2 for best-in-class reasoning capabilities
ORCHESTRATOR_MODEL = "gpt-5.2"

# Verification - checks claims against evidence
# Uses gpt-5-mini for reliable verification at moderate cost
VERIFICATION_MODEL = "gpt-5-mini"

# Generation - generates briefing section content
# Uses gpt-5-mini for quality output
GENERATION_MODEL = "gpt-5-mini"

# RCS (Contextual Summarisation) - scores and summarises chunks
# Uses gpt-4.1-mini for cost efficiency on high-volume scoring
RCS_MODEL = "gpt-4.1-mini"

# Model temperature settings
ORCHESTRATOR_TEMPERATURE = 0.0  # Deterministic tool selection
VERIFICATION_TEMPERATURE = 0.0  # Deterministic verification
GENERATION_TEMPERATURE = 0.3  # Slight creativity for prose


def get_model_config() -> dict:
    """Get the full model configuration as a dictionary.

    Returns:
        Dictionary with model configuration for all components.
    """
    return {
        "orchestrator": {
            "model": ORCHESTRATOR_MODEL,
            "temperature": ORCHESTRATOR_TEMPERATURE,
        },
        "verification": {
            "model": VERIFICATION_MODEL,
            "temperature": VERIFICATION_TEMPERATURE,
        },
        "generation": {
            "model": GENERATION_MODEL,
            "temperature": GENERATION_TEMPERATURE,
        },
        "rcs": {
            "model": RCS_MODEL,
            "temperature": 0.0,
        },
    }
