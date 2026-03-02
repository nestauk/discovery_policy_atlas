import type React from "react";

export interface DocumentTooltipData {
  evidence_category?: string | null;
  evidence_category_reasoning?: string | null;
  evidence_strength_justification?: string | null;
  impact_score_label?: string | null;
  impact_score_breakdown?: Record<string, unknown> | null;
  transferability_score?: number | null;
  transferability_breakdown?: Record<string, unknown> | null;
}

export function getEvidenceCategoryTooltipContent(
  category?: string | null,
  reasoning?: string | null
): React.ReactNode | undefined {
  if (!category) return undefined;
  const cleanReasoning = typeof reasoning === "string" ? reasoning.trim() : "";
  return cleanReasoning ? `${category}\n\n${cleanReasoning}` : category;
}

export function getEvidenceStrengthTooltipContent(
  justification?: string | null
): React.ReactNode | undefined {
  if (typeof justification !== "string") return undefined;
  const clean = justification.trim();
  return clean || undefined;
}

type OutcomeDriver = {
  outcome: string;
  netContribution: number;
  avgSimilarity: number | null;
  magnitudeEstimate: string | null;
};

const showCalcDetails = process.env.NEXT_PUBLIC_SHOW_IMPACT_SCORE_DETAILS === "true";

function effectLabel(netMag: number): string {
  const abs = Math.abs(netMag);
  const strength =
    abs >= 0.66
      ? "substantial"
      : abs >= 0.5
        ? "large"
        : abs >= 0.33
          ? "moderate"
          : abs >= 0.12
            ? "marginal"
            : "no clear";
  if (abs < 0.12) return "Mixed / no clear effect";
  if (netMag > 0) return `${strength} positive effect`;
  return `${strength} negative effect`;
}

function fitLabel(t: number): string {
  if (t >= 0.75) return "Good fit";
  if (t >= 0.5) return "Moderate fit";
  return "Limited fit";
}

function causalityStrengthLabel(avg: number): string {
  if (avg >= 0.95) return "Strong";
  if (avg >= 0.85) return "Moderate";
  return "Weak";
}

function matchLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "Unknown";
  const v = value.trim().toLowerCase();
  if (v === "match") return "Match";
  if (v === "similar") return "Similar";
  if (v === "comparable") return "Comparable";
  if (v === "partial") return "Partial";
  if (v === "mismatch") return "Mismatch";
  return "Unknown";
}

function magnitudeLabel(value: string | null): string | null {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  if (v === "transformational") return "substantial";
  if (v === "substantial") return "large";
  return v;
}

export function getImpactScoreTooltipContent(
  record: DocumentTooltipData
): React.ReactNode | undefined {
  const breakdown = record.impact_score_breakdown;
  const tBreakdown = record.transferability_breakdown;
  if (!breakdown && !tBreakdown && !record.impact_score_label) {
    return undefined;
  }

  const b =
    breakdown && typeof breakdown === "object"
      ? (breakdown as Record<string, unknown>)
      : null;
  const tb =
    tBreakdown && typeof tBreakdown === "object"
      ? (tBreakdown as Record<string, unknown>)
      : null;

  const note = b && typeof b.note === "string" ? b.note : null;
  const netMag = b && typeof b.net_magnitude === "number" ? b.net_magnitude : null;
  const outcomesUsed = b && typeof b.outcomes_used === "number" ? b.outcomes_used : null;
  const avgCausalWeight =
    b && typeof b.avg_causal_weight === "number" ? b.avg_causal_weight : null;

  const geo = tb ? matchLabel(tb.geography) : "Unknown";
  const pop = tb ? matchLabel(tb.population) : "Unknown";
  const setting = tb ? matchLabel(tb.inner_setting) : "Unknown";
  const constraintsProvided = tb ? tb.constraints_provided === true : false;
  const exceedsConstraintsRaw = tb ? tb.exceeds_constraints : null;
  const constraintLevelsRaw = tb ? tb.constraint_levels : null;
  const implementationEvidenceRaw = tb ? tb.implementation_evidence : null;
  const extractedContextRaw = tb ? tb.extracted_context : null;
  const exceededConstraints =
    exceedsConstraintsRaw && typeof exceedsConstraintsRaw === "object"
      ? Object.entries(exceedsConstraintsRaw as Record<string, unknown>)
          .filter(([, v]) => v === true)
          .map(([k]) => k)
      : [];
  const constraintLevels =
    constraintLevelsRaw && typeof constraintLevelsRaw === "object"
      ? (constraintLevelsRaw as Record<string, unknown>)
      : {};
  const implementationEvidence =
    implementationEvidenceRaw && typeof implementationEvidenceRaw === "object"
      ? (implementationEvidenceRaw as Record<string, unknown>)
      : {};
  const extractedContext =
    extractedContextRaw && typeof extractedContextRaw === "object"
      ? (extractedContextRaw as Record<string, unknown>)
      : {};

  const transferability =
    typeof record.transferability_score === "number" ? record.transferability_score : null;

  let drivers: OutcomeDriver[] = [];
  const outcomeBreakdown = b?.outcome_breakdown;
  if (Array.isArray(outcomeBreakdown) && outcomeBreakdown.length > 0) {
    const grouped = new Map<
      string,
      { net: number; simSum: number; simCount: number; mag: string | null; magWeight: number }
    >();
    for (const item of outcomeBreakdown) {
      if (!item || typeof item !== "object") continue;
      const obj = item as Record<string, unknown>;
      const outcome = typeof obj.outcome === "string" ? obj.outcome : "";
      const contribution = typeof obj.contribution === "number" ? obj.contribution : null;
      const similarity = typeof obj.similarity === "number" ? obj.similarity : null;
      const magnitudeEstimate = typeof obj.magnitude === "string" ? obj.magnitude : null;
      if (!outcome || contribution == null) continue;
      const existing =
        grouped.get(outcome) || { net: 0, simSum: 0, simCount: 0, mag: null, magWeight: 0 };
      existing.net += contribution;
      if (similarity != null) {
        existing.simSum += similarity;
        existing.simCount += 1;
      }
      const absWeight = Math.abs(contribution);
      if (absWeight > existing.magWeight && magnitudeEstimate) {
        existing.mag = magnitudeEstimate;
        existing.magWeight = absWeight;
      }
      grouped.set(outcome, existing);
    }
    const hasTargetOutcomes = outcomeBreakdown.some((item) => {
      const obj = item as Record<string, unknown>;
      const sim = typeof obj.similarity === "number" ? obj.similarity : null;
      return sim != null && sim < 0.999;
    });

    drivers = Array.from(grouped.entries())
      .map(([outcome, meta]) => ({
        outcome,
        netContribution: meta.net,
        avgSimilarity: meta.simCount ? meta.simSum / meta.simCount : null,
        magnitudeEstimate: meta.mag,
      }))
      .sort((a, b) => {
        if (hasTargetOutcomes) {
          const simA = a.avgSimilarity ?? 0;
          const simB = b.avgSimilarity ?? 0;
          if (Math.abs(simA - simB) > 0.1) {
            return simB - simA;
          }
        }
        return Math.abs(b.netContribution) - Math.abs(a.netContribution);
      })
      .slice(0, 2);
  }

  const bestMatch = (() => {
    if (!Array.isArray(outcomeBreakdown) || !outcomeBreakdown.length) return null;
    let max = 0;
    let causalWeight: number | null = null;
    for (const item of outcomeBreakdown) {
      const obj = item as Record<string, unknown>;
      const sim = typeof obj.similarity === "number" ? obj.similarity : 0;
      if (sim > max) {
        max = sim;
        causalWeight = typeof obj.causal_weight === "number" ? obj.causal_weight : null;
      }
    }
    return max > 0 ? { similarity: max, causalWeight } : null;
  })();

  const showOutcomeMatch = bestMatch != null && bestMatch.similarity < 0.999;
  const outcomeMatchLabel = (sim: number): string => {
    if (sim >= 0.85) return "Direct match";
    if (sim >= 0.75) return "Proxy measure";
    if (sim >= 0.5) return "Contributing factor";
    if (sim >= 0.2) return "Weak link";
    return "Unrelated";
  };

  const filteredCausalAverage = (() => {
    if (!Array.isArray(outcomeBreakdown) || !outcomeBreakdown.length) return null;
    let sum = 0;
    let count = 0;
    for (const item of outcomeBreakdown) {
      const obj = item as Record<string, unknown>;
      const included = obj.included_in_score === true;
      const causalWeight = typeof obj.causal_weight === "number" ? obj.causal_weight : null;
      if (included && causalWeight != null) {
        sum += causalWeight;
        count += 1;
      }
    }
    return count ? sum / count : null;
  })();

  const headerLabel =
    typeof record.impact_score_label === "string" && record.impact_score_label.trim()
      ? record.impact_score_label
      : "Impact";

  return (
    <div className="space-y-2">
      <div className="font-medium">{headerLabel}</div>
      {note ? <div className="text-neutral-200">{note}</div> : null}
      <div className="space-y-1">
        {netMag != null ? (
          <div>
            <span className="font-medium">Net effect:</span> {effectLabel(netMag)}
          </div>
        ) : null}
        {avgCausalWeight != null || filteredCausalAverage != null || bestMatch?.causalWeight != null ? (
          <div>
            <span className="font-medium">Causality strength:</span>{" "}
            {causalityStrengthLabel(
              bestMatch?.causalWeight ?? filteredCausalAverage ?? avgCausalWeight ?? 0
            )}
          </div>
        ) : null}
        {transferability != null ? (
          <div>
            <span className="font-medium">Fit to your context:</span> {fitLabel(transferability)} ({geo} geography, {pop} population, {setting} setting)
          </div>
        ) : (
          <div>
            <span className="font-medium">Fit to your context:</span> Unknown ({geo} geography, {pop} population, {setting} setting)
          </div>
        )}
        {showOutcomeMatch && bestMatch != null ? (
          <div>
            <span className="font-medium">Outcome match:</span> {outcomeMatchLabel(bestMatch.similarity)}
          </div>
        ) : null}
        {constraintsProvided ? (
          <div>
            <span className="font-medium">Implementation constraints:</span>{" "}
            {(["cost", "staffing", "implementation_complexity"] as const)
              .filter((dim) => constraintLevels[dim])
              .map((dim) => {
                const rawValue = implementationEvidence[dim] as string | null | undefined;
                const valueLabel = rawValue ? rawValue.toLowerCase() : "unknown";
                const label = dim === "implementation_complexity" ? "complexity" : dim;
                if (!rawValue) return `${label}: unknown`;
                const status = exceededConstraints.includes(dim) ? "exceeds" : "within";
                return `${label}: ${valueLabel} (${status})`;
              })
              .join(", ") || "Within your constraints"}
          </div>
        ) : null}
        {typeof outcomesUsed === "number" ? (
          <div>
            <span className="font-medium">Primary outcomes:</span> {outcomesUsed}
          </div>
        ) : null}
      </div>
      {drivers.length ? (
        <div className="space-y-1">
          <div className="font-medium">Key outcomes</div>
          <ul className="list-disc pl-4 space-y-0.5">
            {drivers.map((d) => {
              const direction =
                d.netContribution > 0.12
                  ? "positive"
                  : d.netContribution < -0.12
                    ? "negative"
                    : "mixed/unclear";
              const displayMag = magnitudeLabel(d.magnitudeEstimate);
              const mag = displayMag ? ` (${displayMag})` : "";
              return (
                <li key={d.outcome}>
                  {d.outcome}: {direction}
                  {mag}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {showCalcDetails ? (
        <div className="border-t border-neutral-700 pt-2 space-y-1">
          <div className="font-medium">Calculation details (dev)</div>
          <div>net_magnitude: {netMag != null ? netMag.toFixed(3) : "n/a"}</div>
          <div>transferability: {transferability != null ? transferability.toFixed(3) : "n/a"}</div>
          <div>avg_causal_weight: {avgCausalWeight != null ? avgCausalWeight.toFixed(3) : "n/a"}</div>
          <div>context: geography={geo}, population={pop}, setting={setting}</div>
          <div>
            extracted: countries={JSON.stringify(extractedContext.countries ?? [])}, populations={JSON.stringify(extractedContext.populations ?? [])}, settings={JSON.stringify(extractedContext.settings ?? [])}
          </div>
          <div>
            {`constraints: cost=${String(constraintLevels?.cost ?? "n/a")}, staffing=${String(constraintLevels?.staffing ?? "n/a")}, complexity=${String(constraintLevels?.implementation_complexity ?? "n/a")}`}
          </div>
          <div>
            {`evidence: cost=${String(implementationEvidence?.cost ?? "n/a")}, staffing=${String(implementationEvidence?.staffing ?? "n/a")}, complexity=${String(implementationEvidence?.implementation_complexity ?? "n/a")}`}
          </div>
          {showOutcomeMatch && bestMatch != null ? (
            <div>
              best_outcome_similarity: {bestMatch.similarity.toFixed(2)} ({outcomeMatchLabel(bestMatch.similarity)})
            </div>
          ) : null}
          {drivers.length ? (
            <div>
              drivers: {drivers.map((d) => `${d.outcome}=${d.netContribution.toFixed(2)}`).join(" | ")}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
