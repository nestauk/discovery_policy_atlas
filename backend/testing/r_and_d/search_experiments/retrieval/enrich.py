"""Abstract-coverage classification for Arms A/B (OpenAlex) — measure, don't resolve (spec §4.4).

§4.4 frames abstract enrichment as a "measured trigger": use a cheap resolver, then *measure
whether that is enough*. We take the measure-first half literally and DROP the resolver half
(decision 2026-06-22, spec owner) — for two reasons that make a resolver poor value here:

  - **Crossref-by-DOI yields almost nothing on top of OpenAlex.** OpenAlex already ingests its
    abstracts FROM Crossref (§4.4's own caveat), so papers missing an abstract in OpenAlex are
    disproportionately ones Crossref also lacks — a near-empty intersection for real network cost.
  - **Europe PMC is the wrong corpus.** It is PubMed/PMC (biomedical) literature; coverage of
    general policy / social-science evidence is thin and skewed, so it can't be relied on for
    Nesta's query distribution.

So this module does ONE thing: flag each candidate's `text_basis` as `"abstract"` or
`"title_only"` and report the **title-only fraction** — the signal §4.4 actually needs (the
judge under-crediting check, and the §4.7 "metrics with/without title-only papers" breakdown).
The judge already handles the `title_only` flag (judge.py `_format_paper`). Some OpenAlex
coverage will simply be title-only, and that's recorded as a finding, not patched over.

> If a real run shows the title-only fraction threatening the metrics (provisional §4.4 bar:
> >15% of judged candidates, or an arm-asymmetry that could bias the comparison), THAT is when
> to revisit — and the better resolver then is S2 (already wired for Arm C, highest coverage),
> weighed against the A/B source-boundary cost (§4.4), not Crossref/EBI.

REPL usage (no main()/argparse — spec conventions):
    from retrieval.enrich import classify_text_basis
    stats = classify_text_basis(candidates)   # sets cand.text_basis in place
    stats.title_only_fraction                  # watch against the §4.4 >15% bar
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from source import Candidate

logger = logging.getLogger(__name__)


def has_abstract(cand: Candidate) -> bool:
    """True if the candidate carries usable abstract text.

    Treats OpenAlexService's "No abstract available" sentinel and blank/whitespace as missing,
    so a sentinel string never masquerades as a real abstract to the judge.
    """
    a = (cand.abstract or "").strip()
    return bool(a) and a.lower() != "no abstract available"


@dataclass
class CoverageStats:
    """Abstract-coverage outcome for a candidate set — the §4.4 measured-trigger signal."""

    n_total: int = 0
    n_abstract: int = 0  # judged on title + abstract
    n_title_only: int = 0  # judged on title alone (no usable abstract)

    @property
    def title_only_fraction(self) -> float:
        """Fraction left title-only (§4.4 provisional trigger bar: > 0.15)."""
        return self.n_title_only / self.n_total if self.n_total else 0.0


def classify_text_basis(candidates: list[Candidate]) -> CoverageStats:
    """Set `text_basis` (`"abstract"` | `"title_only"`) on each candidate in place; report coverage.

    No network, no resolver (see module docstring) — purely classifies what OpenAlex returned and
    leaves the rest as an honest title-only finding. Idempotent: a candidate already flagged
    `tldr`/`snippet` (Arm C) is left as-is, since this is the Arm A/B classifier.
    """
    stats = CoverageStats(n_total=len(candidates))
    for cand in candidates:
        if has_abstract(cand):
            cand.text_basis = cand.text_basis or "abstract"
            stats.n_abstract += 1
        else:
            # Don't clobber an Arm-C native flag; only A/B candidates reach here unflagged.
            if cand.text_basis not in ("tldr", "snippet"):
                cand.text_basis = "title_only"
            stats.n_title_only += 1
    logger.info(
        "Abstract coverage: %d total, %d with abstract, %d title-only (%.1f%%)",
        stats.n_total,
        stats.n_abstract,
        stats.n_title_only,
        100 * stats.title_only_fraction,
    )
    return stats
