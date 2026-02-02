from __future__ import annotations

import re
from typing import Any, List, Tuple

from app.services.synthesis.schemas import (
    InterventionTableRow,
    RecommendationItem,
    SynthesisSection,
)


def strip_leading_label(text: str, labels: List[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    for label in labels:
        cleaned = re.sub(rf"^\s*{re.escape(label)}\s*", "", cleaned, flags=re.I)
    return cleaned.strip()


def strip_inline_labels(text: str, labels: List[str]) -> str:
    if not text:
        return ""
    cleaned = text
    for label in labels:
        cleaned = re.sub(rf"\b{re.escape(label)}\s*", "", cleaned, flags=re.I)
    return cleaned.strip()


def clean_rec_title(title: str) -> str:
    cleaned = (title or "").strip()
    cleaned = cleaned.strip("*").strip()
    cleaned = re.sub(r"[*_`]+$", "", cleaned).strip()
    return cleaned


def extract_citation_numbers(text: str) -> List[int]:
    matches = re.findall(r"\[(\d+)\]", text)
    return [int(m) for m in matches if int(m) > 0]


def parse_intervention_table(
    content: str, interventions: List
) -> List[InterventionTableRow]:
    rows: List[InterventionTableRow] = []
    lines = content.strip().split("\n")
    table_started = False

    for line in lines:
        if "|" not in line:
            continue
        if set(line.replace("|", "").replace("-", "").replace(" ", "")) == set():
            table_started = True
            continue
        if not table_started:
            table_started = True
            continue

        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [c.strip() for c in stripped.split("|")]
        if len(cells) >= 2:
            citation_nums = extract_citation_numbers(line)
            intervention_name = cells[0] if len(cells) > 0 else ""
            context = cells[1] if len(cells) > 1 else ""

            key_study_description = ""
            impact_narrative = ""

            if len(cells) >= 5:
                key_study_description = cells[2] if len(cells) > 2 else ""
                impact_narrative = cells[3] if len(cells) > 3 else ""
            else:
                impact_narrative = cells[2] if len(cells) > 2 else ""

            key_study_citation = None
            if key_study_description:
                key_cits = extract_citation_numbers(key_study_description)
                key_study_citation = key_cits[0] if key_cits else None

            rows.append(
                InterventionTableRow(
                    intervention_name=intervention_name,
                    citation_numbers=citation_nums,
                    context=context,
                    key_study_description=key_study_description,
                    key_study_citation=key_study_citation,
                    impact_narrative=impact_narrative,
                    outcome_effects=[],
                )
            )

    if not rows and interventions:
        for intervention in interventions[:10]:
            rows.append(
                InterventionTableRow(
                    intervention_name=getattr(
                        intervention, "intervention_name", "Unknown"
                    ),
                    citation_numbers=[],
                    context=getattr(intervention, "brief_description", ""),
                    impact_narrative="",
                    outcome_effects=[],
                )
            )

    return rows


def split_recommendation(text: str) -> Tuple[str, str]:
    if ":" in text[:60]:
        parts = text.split(":", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    if ". " in text[:60]:
        parts = text.split(". ", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    words = text.split()
    title = " ".join(words[:6])
    description = " ".join(words[6:]) if len(words) > 6 else ""
    return title, description


def parse_recommendations(content: str) -> List[RecommendationItem]:
    rec_pattern = re.compile(r"^(?:\*\*)?(\d+)[.\)]\s*")

    recommendations: List[RecommendationItem] = []
    lines = content.strip().split("\n")
    current_rec_lines: List[str] = []
    current_rec_number = 0

    def _parse_rec_block(rec_number: int, rec_lines: List[str]) -> None:
        if not rec_lines:
            return
        joined = "\n".join(rec_lines).strip()
        impl = ""
        remaining_lines: List[str] = []
        for ln in joined.splitlines():
            s = ln.strip()
            if not s:
                continue
            lowered = s.lower()
            if lowered.startswith("implementation option:"):
                impl = s.split(":", 1)[1].strip() if ":" in s else ""
            elif lowered.startswith("- implementation option:"):
                impl = s.split(":", 1)[1].strip() if ":" in s else ""
            else:
                remaining_lines.append(s)

        full_text = " ".join(remaining_lines)
        title, description = split_recommendation(full_text)
        citations = extract_citation_numbers((description or "") + " " + (impl or ""))
        recommendations.append(
            RecommendationItem(
                number=rec_number,
                title=title,
                description=description,
                implementation_option=impl,
                citation_numbers=citations,
            )
        )

    for line in lines:
        stripped = line.strip()
        match = rec_pattern.match(stripped)
        if match:
            if current_rec_lines:
                _parse_rec_block(current_rec_number, current_rec_lines)
            current_rec_number = int(match.group(1))
            remaining = stripped[match.end() :].lstrip("* ").rstrip("*")
            current_rec_lines = [remaining] if remaining else []
        elif current_rec_lines and stripped:
            current_rec_lines.append(stripped)

    if current_rec_lines:
        _parse_rec_block(current_rec_number, current_rec_lines)

    return recommendations


def parse_synthesis_sections(
    synthesis_outputs: List[Tuple[str, Any]]
) -> List[SynthesisSection]:
    sections: List[SynthesisSection] = []

    for title, output in synthesis_outputs:
        content = (output.content or "").strip()
        if not content:
            continue

        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        lowered_title = title.lower().rstrip(":")
        while lines and (
            lines[0].lower().rstrip(":") == lowered_title
            or lines[0].lower().startswith(lowered_title)
        ):
            lines.pop(0)

        bullet_lines = [ln for ln in lines if ln.startswith("-") or ln.startswith("*")]

        if bullet_lines and len(bullet_lines) >= max(2, int(0.6 * len(lines))):
            bullets = [ln.lstrip("-* ").strip() for ln in bullet_lines]
            sections.append(
                SynthesisSection(
                    title=title,
                    content_type="bullets",
                    bullets=bullets,
                    citation_numbers_used=output.citations_used,
                )
            )
        else:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            if not paragraphs and lines:
                paragraphs = [" ".join(lines)]

            sections.append(
                SynthesisSection(
                    title=title,
                    content_type="paragraphs",
                    paragraphs=paragraphs,
                    citation_numbers_used=output.citations_used,
                )
            )

    return sections
