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


def get_model_config() -> dict:
    """Get the full model configuration as a dictionary.

    Returns:
        Dictionary with model configuration for all components.
    """
    return {
        "orchestrator": {
            "model": ORCHESTRATOR_MODEL,
        },
        "verification": {
            "model": VERIFICATION_MODEL,
        },
        "generation": {
            "model": GENERATION_MODEL,
        },
        "rcs": {
            "model": RCS_MODEL,
        },
    }
