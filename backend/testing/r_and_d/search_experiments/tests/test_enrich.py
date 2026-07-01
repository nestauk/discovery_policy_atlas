"""Offline tests for retrieval.enrich — abstract-coverage classification (§4.4, measure-not-resolve).

The §4.4 deliverable is the title-only FRACTION (the judge under-crediting check + the §4.7
with/without-title-only breakdown), so these pin: the missing-abstract detection (incl. OpenAlex's
"No abstract available" sentinel), the text_basis flagging, the fraction maths, and that an
Arm-C native flag (tldr/snippet) is never clobbered by the A/B classifier.
"""

from __future__ import annotations

from retrieval.enrich import classify_text_basis, has_abstract
from source import Candidate


def test_has_abstract_treats_sentinel_and_blank_as_missing():
    assert not has_abstract(Candidate("W1", abstract=None))
    assert not has_abstract(Candidate("W1", abstract="   "))
    assert not has_abstract(Candidate("W1", abstract="No abstract available"))
    assert not has_abstract(
        Candidate("W1", abstract="NO ABSTRACT AVAILABLE")
    )  # case-insensitive
    assert has_abstract(Candidate("W1", abstract="A real abstract."))


def test_classify_sets_text_basis_and_counts():
    cands = [
        Candidate("W1", abstract="real text"),
        Candidate("W2", abstract=None),
        Candidate("W3", abstract="No abstract available"),
    ]
    stats = classify_text_basis(cands)
    assert cands[0].text_basis == "abstract"
    assert cands[1].text_basis == "title_only"
    assert cands[2].text_basis == "title_only"
    assert (stats.n_total, stats.n_abstract, stats.n_title_only) == (3, 1, 2)
    assert abs(stats.title_only_fraction - 2 / 3) < 1e-9


def test_classify_empty_pool_fraction_is_zero():
    stats = classify_text_basis([])
    assert stats.n_total == 0 and stats.title_only_fraction == 0.0


def test_classify_does_not_clobber_arm_c_native_flags():
    # An Arm-C candidate with no abstract but a tldr/snippet basis must keep that flag.
    c = Candidate("W1", abstract=None, text_basis="tldr")
    classify_text_basis([c])
    assert c.text_basis == "tldr"
