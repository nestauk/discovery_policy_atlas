"""Pydantic models for structured C/M extraction during forecast deep dive."""

from __future__ import annotations

from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, Field


class EvidenceBasis(str, Enum):
    """Provenance tag indicating how a fragment is grounded in the evidence."""

    EMPIRICAL = "empirical"
    AUTHOR_HYPOTHESIS = "author_hypothesis"
    THEORY_BACKGROUND = "theory_background"


class ObservedContext(BaseModel):
    """Context in which the intervention was studied."""

    setting: str = Field(
        description="Where the intervention was implemented (e.g. 'primary schools in London')"
    )
    population: str = Field(description="Who was targeted (e.g. 'children aged 5-11')")
    delivery_features: List[str] = Field(
        default_factory=list,
        description="Key implementation features (e.g. 'trained facilitators', 'weekly sessions')",
    )


class MechanismExtraction(BaseModel):
    """Working mechanism summary refined from evidence fragments."""

    summary: str = Field(
        description="One-sentence mechanism: what the intervention does and WHY it produces the outcome"
    )
    confidence: Literal[
        "explicit", "mediator_supported", "weak", "insufficient"
    ] = Field(
        description="How well the evidence supports this mechanism claim",
    )


class Mediator(BaseModel):
    """An intermediate variable through which the intervention acts."""

    name: str = Field(description="The mediating factor (e.g. 'teacher confidence')")
    direction: Literal["increase", "decrease", "mixed", "unclear"] = Field(
        description="Direction of the mediator's effect",
    )
    quote: str = Field(
        description="Verbatim quote from the evidence supporting this mediator"
    )
    basis: EvidenceBasis = Field(
        description="How this claim is grounded in the evidence"
    )


class SupportFactor(BaseModel):
    """A condition that must be present for the mechanism to operate."""

    factor: str = Field(
        description="The enabling condition (e.g. 'dedicated training budget')"
    )
    quote: str = Field(description="Verbatim quote from the evidence")
    basis: EvidenceBasis = Field(
        description="How this claim is grounded in the evidence"
    )


class ModeratorOrDealbreaker(BaseModel):
    """A factor that strengthens, weakens, or blocks transferability."""

    item: str = Field(description="The moderating factor (e.g. 'class size above 30')")
    effect: Literal["helps", "blocks", "mixed", "unknown"] = Field(
        description="Whether this factor helps or hinders transferability",
    )
    quote: str = Field(description="Verbatim quote from the evidence")
    basis: EvidenceBasis = Field(
        description="How this claim is grounded in the evidence"
    )


class InterventionCMExtraction(BaseModel):
    """Complete C/M extraction for a single intervention from project evidence."""

    draft_programme_theory: str = Field(
        description="One-sentence draft theory: 'This intervention works by X, through Y, if Z is present'",
    )
    observed_contexts: List[ObservedContext] = Field(
        description="Contexts in which this intervention was studied (one per distinct study setting)",
    )
    mechanism: MechanismExtraction
    mediators: List[Mediator] = Field(default_factory=list)
    support_factors: List[SupportFactor] = Field(default_factory=list)
    moderators_or_dealbreakers: List[ModeratorOrDealbreaker] = Field(
        default_factory=list
    )


class CriticFlag(BaseModel):
    """A single issue found by the critic pass."""

    issue: str = Field(description="What is wrong or unsupported")
    field: str = Field(
        description="Which extraction field this affects (e.g. 'mechanism', 'support_factors[0]')"
    )
    severity: Literal["downgrade", "note"] = Field(
        description="'downgrade' = confidence or a factor should be weakened; 'note' = flag for user but no change needed",
    )
    suggestion: str = Field(description="What should change")


class CriticResult(BaseModel):
    """Output of the critic pass over a C/M extraction."""

    flags: List[CriticFlag] = Field(default_factory=list)
    revised_mechanism_confidence: Literal[
        "explicit", "mediator_supported", "weak", "insufficient"
    ] = Field(
        description="Mechanism confidence after critic review — can only stay the same or go down, never up",
    )
    missing_dealbreakers: List[str] = Field(
        default_factory=list,
        description="Dealbreakers the extraction missed that the user's context suggests (e.g. 'budget limited but intervention requires significant funding')",
    )
