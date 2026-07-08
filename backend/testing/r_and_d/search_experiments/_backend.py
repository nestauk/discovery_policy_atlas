"""The single seam to the production backend (`app.*`) and `pyalex`.

Every accessor here lazy-imports its backend dependency *inside* the function, so importing this
module — and any experiment module that does `from _backend import …` at the top — pulls **no**
backend env and **no** heavy deps (langchain/pyalex/supabase). That's what keeps the pure-logic
modules and their offline tests import-clean and fast.

Before this seam, those lazy `from app.… import …` statements were scattered through function
bodies and `__init__`s all over the experiment (FINDINGS 2026-06-26 tech-debt). Now the app-coupling
lives in exactly one file; callers get a clean module-top `from _backend import get_llm` and call it.
The laziness is unchanged (the import still happens on first *call*, not on import) — so behaviour and
test characteristics are identical; only the location of the `from app.…` lines moved.
"""

from __future__ import annotations


# --- LLM ------------------------------------------------------------------------------------- #
def get_llm(model: str, temperature: float):
    """Backend `get_llm` — returns a chat model (callers add `.with_structured_output(...)`)."""
    from app.utils.llm.llm_utils import get_llm as _get_llm

    return _get_llm(model, temperature)


def get_llm_processor_cls():
    """The batched `LLMProcessor` class (judge.py instantiates it with its own kwargs)."""
    from app.utils.llm.batch_check import LLMProcessor

    return LLMProcessor


# --- config ---------------------------------------------------------------------------------- #
def get_settings():
    """Backend Pydantic `settings` (reads backend/.env)."""
    from app.core.config import settings

    return settings


# --- OpenAlex (Arms A/B) --------------------------------------------------------------------- #
def get_openalex_service():
    """A fresh `OpenAlexService` (its __init__ configures the PyAlex global: polite-pool email + key).

    Then set the PyAlex retry from CONFIG — now production's values (3 / 0.5), reverted from the 06-26
    hardening since the per-variant catch-and-skip + 1 req/s gate are the resilience now, not a long
    backoff (FINDINGS 2026-06-30) — plus 502/504 in the forcelist (transient gateway timeouts are
    retryable). PyAlex `config` is a global read at request time, so this also covers Arm B's snowball
    `Works` calls; `__init__` resets it, so we re-apply after every construction.

    Also install the heavy-query rate limit (>5-operator queries → 1 req/s; FINDINGS 2026-06-30), which
    patches the shared pyalex request chokepoint and so likewise covers every Arm A/B call path including
    Arm B's snowball `Works` calls (`OpenAlexSource.__init__` constructs the service before snowball runs).
    Idempotent — re-applying after every construction is a no-op.
    """
    import pyalex
    from app.services.openalex import OpenAlexService

    from config import CONFIG
    from retrieval._openalex_throttle import install_rate_limit

    svc = OpenAlexService()
    pyalex.config.max_retries = CONFIG.openalex_max_retries
    pyalex.config.retry_backoff_factor = CONFIG.openalex_retry_backoff_factor
    pyalex.config.retry_http_codes = list(
        CONFIG.openalex_retry_http_codes
    )  # +502/504 (transient gateway)
    install_rate_limit(CONFIG.openalex_min_request_interval_s)
    return svc


def get_sanitize_query():
    """The production `sanitize_openalex_query` function (cache callers store it once)."""
    from app.services.openalex import sanitize_openalex_query

    return sanitize_openalex_query


def get_references_service(export_dir: str):
    """A `ReferencesService` pointed at `export_dir` (its __init__ mkdirs that dir)."""
    from app.services.analysis.references import ReferencesService

    return ReferencesService(export_dir=export_dir)


def get_boolean_clauses():
    """The SR/RCT fanout clause constants + variant-priority map: (SR_CLAUSE, RCT_CLAUSE, VARIANT_PRIORITY)."""
    from app.services.analysis.references import (
        RCT_CLAUSE,
        SYSTEMATIC_REVIEW_CLAUSE,
        VARIANT_PRIORITY,
    )

    return SYSTEMATIC_REVIEW_CLAUSE, RCT_CLAUSE, VARIANT_PRIORITY


def get_works_cls():
    """The raw PyAlex `Works` class (snowball graph walks use it directly)."""
    from pyalex import Works

    return Works
