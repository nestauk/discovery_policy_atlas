# Intervention Transferability Framework — Design Spec

**Status**: Draft spec (design only, not yet scoped for implementation)
**Date**: 2026-04-24
**Author**: Aidan Kelly, with Claude Code
**Source framework**: `docs/PA_Intervention_Transferability_Framework.md`
**Current prototype**: PR #153 (`chatbot-transferability` branch)

---

## 1. Purpose and framing

This is a **thinking tool** for policymakers, not a recommendation engine or prediction system. The framework structures the question "would this intervention work in my context?" into three independent conditions that all need to hold. The system's scores are presented as **hypotheses** — structured starting points for the user's own judgment, not verdicts.

The framework outputs should state the confidence level directly ("This analysis has [level] confidence that [intervention design] would work in your context") and then invite exploration ("Is there anything you'd like to explore further or any questions about the assessment?").

### What this replaces

PR #153 implements a prototype transferability assessment in the chatbot. It uses the three-leg structure but relies on prompt engineering for scoring, producing non-reproducible narrative assessments. This spec describes the systematic version: deterministic where possible, structured extraction where not, and always traceable to the evidence.

### Horizontal search limitation

This framework assesses the intervention in isolation. Interactions with concurrent policies operating in the same environment are not considered. This caveat should be stated explicitly in every assessment output.

---

## 2. Unit of analysis

**Theme x Outcome x Intervention Cluster**

The assessment progressively narrows through three levels:

1. **Intervention theme** (fast screen) — clusters produced during synthesis (e.g., "Sugar/HFSS taxes"). Used for triage.
2. **Outcome** (selection step) — which outcome within the theme the user cares about (e.g., "industry reformulation"). Scopes the contributing studies.
3. **Intervention cluster** (emerges from reconciliation) — within the outcome's contributing studies, the reconciliation step may surface distinct intervention designs (e.g., "tiered levies" vs "flat-rate taxes"). The user picks the one closest to what they're considering.

The full three-leg assessment runs at the **cluster level** — the most specific unit. This ensures that the 'it worked somewhere' scores, mechanisms, and support factors all describe the same coherent intervention, not a mix of dissimilar designs.

### How intervention variant clusters emerge

Clusters are NOT pre-defined by the synthesis pipeline or by the user (although this might be a useful step to do within pipeline if valuable). They emerge naturally from the Leg 2 reconciliation step:

1. Per-study extraction runs on all documents contributing to the selected outcome.
2. The reconciliation LLM compares the per-study extractions and groups by intervention design similarity.
3. If all studies describe the same intervention design → one cluster, proceed directly.
4. If studies describe meaningfully different designs → present the clusters to the user: "The evidence describes two distinct intervention designs: [A] supported by [studies], [B] supported by [studies], alongside a verdict in terms of how it contributes to the outcome (similar to what has been done for the outcome themes). Asks Policymaker which of them is closer to what they're considering?"
5. The user picks a cluster (or can choose "assess broadly across all" if they prefer the theme-level view).

This solves the variant boundary problem: the system proposes boundaries based on the actual study data, grounded by the mechanism extractions, and the user validates. No pre-clustering pipeline needed.

### Why this matters for scoring

Once the user picks a cluster, **Leg 1 is computed scoped to that cluster's studies only**. The fast-screen interface is for triaging; the deep-dive Leg 1 (cluster-level) is the actual score we use. They may differ — a theme might look strong at triage (7 studies total) but the specific cluster the user cares about might be weaker (2 observational studies). This is correct and important: the user needs to know the 'it works somewhere' assessment for the specific intervention design they're considering, not the theme in general.

### Reconciliation: per-study to cluster

Each leg reconciles differently:

**Leg 1 — Computed at cluster level, deterministic.**
Only the documents in the selected cluster contribute. Effect direction, evidence score, and causality claim are computed from these documents only. This means selecting a different cluster within the same key outcome can produce a different Leg 1 score.

**Leg 2 — Per-study extraction, LLM reconciliation to cluster.**
Each contributing document gets its own extraction (study causal role, transferable causal role, core pathway). The reconciliation step:
- Groups studies by intervention design similarity (this is what surfaces the clusters).
- Within the selected cluster, produces a consensus pathway if studies agree.
- If studies within a cluster still diverge on mechanism details, notes this as reduced confidence.
- The reconciliation step flags where studies converge vs diverge — convergence increases confidence, divergence decreases it.

**Leg 3 — Once on the cluster's reconciled mechanism.**
Support factor extraction (direct + pre-mortem + pathway decomposition) runs once, after Leg 2 reconciliation, against the selected cluster's primary pathway. This is because:
- The pre-mortem asks "what could go wrong in the user's context?" — that question is about the implementation, not the study, so it should run against the transferable mechanism.
- The "by means of what?" pass depends on the transferable causal role, which is a Leg 2 output.
- Per-study factor extraction would create deduplication problems (different studies describing the same factor in different words) without proportional quality gains.
- Study-specific implementation details (e.g., "the UK SDIL required a 2-year lead time") are still captured by the direct extraction pass, which reads all the study text within the cluster.

---

## 3. User flow

```
1. Confirm context
   User confirms or edits: geography, population, setting, desired outcomes.
   Default assumption: UK (tool targets UK policymakers).

2. Fast screen (all themes)
   Comparative table with Leg 1 data at theme level.
   Implicit framing: "Here's what we know about whether these interventions
   work. To assess whether they could work HERE, pick one to deep-dive."
   No explicit "Leg 1/2/3" labels — the structure emerges through the flow.

3. Pick theme
   User selects an intervention theme from the fast screen.

4. Pick outcome (structured UI)
   If the theme has multiple OutcomeThemes linked via intervention_theme_id,
   show a card/dropdown selector — NOT a conversational turn.
   If only one outcome, auto-select and confirm.
   If the user's stated desired outcome clearly maps to one OutcomeTheme,
   auto-select and confirm.

5. Extraction + cluster identification
   Per-study extraction runs internally (≤30s with progress indicator).
   Reconciliation groups studies by intervention design similarity.

   5a. If all studies describe the same intervention design:
       One cluster — proceed directly to assessment (step 6).

   5b. If studies describe distinct intervention designs:
       Present clusters to the user:
       "The evidence describes two distinct intervention designs:
        A. [description] — [N] studies
        B. [description] — [N] studies
        Which one would you like to pick for transferability analysis?"
       User picks a cluster (or "assess broadly across all").

6. Deep dive assessment (scoped to cluster)
   Leg 1 recomputed for the selected cluster's studies only.

   6a. Present Leg 1 + Leg 2 scores upfront:
       - Leg 1 (evidence): recomputed deterministically for cluster.
       - Leg 2 (pathway fit): from cluster's reconciled extraction + critic.
       - Leg 3 (support factors): shown as "not yet assessed".
       Plain language summary + mechanism + core pathway.

   6b. Factor resolution loop (Leg 3):
       Smart defaults pre-fill where possible.
       Ask about remaining unknowns one at a time.
       Re-render factor table and update Leg 3 status on each answer.

   6c. Final assessment:
       All three legs scored. Overall confidence + binding constraint
       in plain language. Score presented as hypothesis.

7. (Optional) Compare interventions
   Side-by-side table of assessed interventions.

```

---

## 4. "It worked somewhere" (Leg 1)

### Purpose

Assess whether there is credible evidence that the intervention improved this specific outcome in at least one setting.

### Inputs (all from existing metadata, scoped to selected cluster)

Leg 1 is only formally computed during the **deep dive**, scoped to the selected intervention cluster. The fast screen does NOT compute a Leg 1 score — it shows evidence badges and effect direction for the user to triage visually.

| Input | Source | Scope |
|-------|--------|-------|
| Effect direction | Per-document `effect_direction` | Computed from cluster's documents for the selected key outcome |
| Evidence score | Per-document `evidence_score` (1-5) | Only documents in the selected cluster |
| Causality claim | Per-document `causality_claim` | Aggregated from cluster's documents for outcomes which contribute to key outcome|

Scoping to the cluster means Leg 1 answers "is there credible evidence that THIS specific intervention design produces THIS outcome?" A different cluster within the same theme x outcome can produce a different Leg 1 score.

### Cluster-level aggregation

Each input is aggregated from per-result data (`ResultItem`) scoped to the cluster's documents and the selected outcome:

| Input | Aggregation method | Rationale |
|-------|-------------------|-----------|
| Effect direction | Ratio-based: positive > 2x negative = positive, else mixed | Same approach as existing synthesis consensus logic |
| Evidence score | Best in cluster (max) | A single strong study establishes "it worked somewhere" |
| Causality claim | Quality-weighted: sum `evidence_score` per claim type, highest weighted total wins | Same approach as existing `compute_causal_mechanism`, run on the cluster's documents only |

The data for all three inputs exists at the per-result level (`ResultItem.effect_direction`, `ResultItem.causality_claim`, per-document `evidence_score`), so cluster-level aggregation is a straightforward subset operation using the same algorithms the synthesis pipeline already uses.

### Scoring algorithm (deterministic, sequential)

This is a sequential ceiling algorithm, not a min of independent scores. Each step constrains the level set by the previous step.

**Step 1 — Effect direction gate:**

| Direction | Result |
|-----------|--------|
| Negative / no change | Ceiling: Low |
| Mixed | Ceiling: Medium |
| Positive (aligned with desired outcome) | Continue |
| Insufficient | Ceiling: Very Low |

**Step 2 — Evidence strength ceiling:**

| Evidence score (best in cluster) | Ceiling |
|-------------------------------|---------|
| 5 | Very High |
| 4 | High |
| 3 | Medium |
| 2 | Low |
| 1 | Very Low |

The current level cannot exceed this ceiling. If direction already capped it lower, it stays lower.

**Step 3 — Causality claim modifier:**

| Causality claim (quality-weighted primary) | Modifier |
|-----------------|----------|
| Attribution | No change |
| Contribution | Drop one level from current |
| Correlation | Drop one level from current AND cap at Medium |

**Leg 1 confidence = the level remaining after all three steps have been applied sequentially.**

Example: direction positive (continue) → evidence score 3 (ceiling Medium) → causality contribution (drop one) → **Low**.

### Fast screen presentation

The fast screen is a visual triage table — no formal scoring. The user picks based on what they see.

| Intervention theme | Outcome evidence base | Does it help? |
|--------------------|----------------------|---------------|
| [name] | [evidence badges: SR/MA (1) RCT (2) etc.] | [plain language effect vs desired outcome] |

Rows are ordered by evidence strength and then tiebreak on number of studies (just how we've ranked the intervention themes), but no Leg 1 score is computed or shown at this stage. The formal Leg 1 score is only computed during deep dive, scoped to the selected cluster.

---

## 5. "It plays the same causal role here and there" (Leg 2)

### Purpose

Assess whether the reason the intervention worked in the study settings could plausibly apply in the user's context.

### Extraction (per-study, internal)

For each contributing document in the theme x outcome, extract:

1. **Study causal role**: What was the intervention trying to do in this study?
2. **Transferable causal role**: The functional job at the level likely to travel to the stated policymaker context (Cartwright vertical search — abstract only until vacuity).
3. **Core pathway**: intervention -> first change -> second change -> outcome (3-4 steps max, single primary pathway).

### Reconciliation and cluster identification

After per-study extraction, the reconciliation step serves two purposes: identifying intervention clusters and producing a consensus pathway within the selected cluster.

1. **Cluster identification**: Group studies by intervention design similarity. If all studies describe the same design, one cluster — proceed. If studies describe distinct designs, present them: "The evidence describes two distinct intervention designs: [A] — [N] studies, [B] — [N] studies as well as whether evidenced positive or not (like done for key outcome themes). Which one would you like to pick for transferability analysis?"
2. **Within-cluster reconciliation**: For the selected cluster, produce a consensus transferable causal role and core pathway. If studies within a cluster still diverge on mechanism details, note this as reduced confidence.

### Abstraction guardrails

The transferable causal role is extracted by the LLM with the following guardrails:

1. **LLM-as-judge**: The critic pass evaluates the abstraction level holistically — is it concrete enough to be useful for the user's context, or has it been abstracted to vacuity?
2. **Specific mechanism of change required**: The role must name a mechanism, not just a direction (e.g., "deterrence through perceived surveillance" not "reduces crime").
3. **Vacuity cap**: If the critic judges the role as vacuous (generic verbs only: improve, support, enhance, promote), Leg 2 is capped at Low.

The framework's own scoring criteria (from the source document) serve as the judge's rubric:
- Too abstract / vacuous -> capped at Low
- Moderately informative -> capped at Medium
- Concrete and decision-relevant -> continue with no ceiling

### Scoring algorithm

Like Leg 1, this is a sequential ceiling algorithm — each step constrains the level set by the previous step. Start at Very High, three steps constrain.

**Step 1 — Transferable causal role specificity:** 
Assessed by critic pass (LLM-as-judge).

| Assessment | Result |
|------------|--------|
| Too abstract / vacuous | Ceiling: Low |
| Moderately informative | Ceiling: High |
| Concrete and decision-relevant | Continue |

**Step 2 — Core pathway plausibility:**
Given the user's outcome, population, and setting, is the step-by-step chain plausible? The current level cannot exceed this ceiling.

| Assessment | Result |
|------------|--------|
| Broken / implausible (one key step unavailable, blocked, contradicted) | Ceiling: Low |
| Partially plausible (broadly makes sense, one+ steps weak) | Ceiling: Medium |
| Plausible end to end (main steps logical and credible) | Continue |

**Step 3 — Context sufficiency:**
Do we know enough about outcome, population, and setting to assess the pathway? The current level cannot exceed this ceiling.

| Context | Result |
|---------|--------|
| Minimal context | Ceiling: Very Low |
| Partial context | Ceiling: Medium |
| Clear enough context | Continue |

**Leg 2 confidence = the level remaining after all three steps have been applied sequentially.**

Example: role concrete (continue) → pathway plausible (continue) → context clear (continue) → **Very High**.

---

## 6. "The support factors are here" (Leg 3)

### Purpose

Assess whether the enabling conditions the intervention depends on exist in the user's context.

### Extraction

Support factors are extracted using a two-pass approach (already implemented in current PR):

**Pass 1 — Direct extraction + "by means of what?"**
What conditions does the evidence say must be present for the mechanism to operate? Given the mechanism and transferable causal role, what must be in place for that causal role to be fulfilled?

**Pass 2 — Pre-mortem**
Imagine this intervention was implemented in a new context and failed. What went wrong? What was missing, unavailable, or blocked?

**Pass 3 — Pathway decomposition**
For each link in the core pathway (from Leg 2), what does that link require? This makes the support factors precise by attaching them to specific pathway steps.

Deduplicate across all passes. Tag each factor with evidence basis (empirical / author_hypothesis / theory_background) and type (essential vs enabling).

### Factor status options

| Status | Meaning | Assigned when |
|--------|---------|---------------|
| Present | Condition exists in user's context | User explicitly confirmed |
| Buildable | Absent but constructable with realistic effort | User said it's missing but could be put in place |
| Absent | Missing and not credibly buildable | User said it's missing, no indication it could be built |
| Unknown | Not yet assessed | Default — user hasn't been asked or said "not sure" |


### Factor resolution loop

Priority order for asking about Unknown factors:
1. Empirical dealbreakers (effect = "blocks", basis = empirical)
2. Empirical support factors
3. Hypothesis-based or theory-based factors

Each turn:
1. Ask: "Does your context include [factor]? If not, is it something you could put in place? This matters because [reason]."
2. Chips: "Yes, we have that" | "No, but we could build it" | "No, we don't" | "Not sure" | "Skip"

Early exit rules:
- Required support factor Absent -> overall Weak. Stop asking.
- Dealbreaker Present -> overall Weak. Stop asking.
- All empirical factors resolved favourably (Present or Buildable for support factors, Absent for dealbreakers) and only hypothesis-based unknowns remain -> "Conditional on unverified assumptions." Offer to continue or stop.
- All factors resolved -> final assessment.

### Scoring

| Status | Result |
|--------|--------|
| Blocked | At least one required support factor is Absent and not buildable |
| Provisional | No known fatal absence but one+ required factors are Unknown |
| Viable | All required factors are Present or Buildable |

Note: If any factors are Buildable, the assessment cannot reach "V high confidence" overall — the final output must name what needs to be built and frame these as implementation requirements.

---

## 7. Combined scoring

**Overall confidence = min(Leg 1 confidence, Leg 2 confidence), capped by Leg 3 status**

| Leg 3 status | Cap |
|-------------|-----|
| Blocked | Overall is Low at best |
| Provisional | Overall is Medium at best |
| Viable | No extra cap |

The min rule is intentional: strong evidence does not compensate for a broken pathway; a good pathway does not compensate for missing factors. These are independent conditions that all need to hold.

### Binding constraint labels (internal)

| Pattern | Label | User action |
|---------|-------|-------------|
| Leg 1 weakest | Evidence-limited | Find stronger studies or pilot carefully |
| Leg 2 weakest | Transfer-limited | Look for a variant whose pathway fits the user's context |
| Leg 3 Blocked/Provisional | Factor-limited | Establish missing factors if buildable, else consider different intervention |
| Multiple legs weak | Multiply-limited | Intervention is likely not a good candidate |
| All legs clear | Well-supported | Move to implementation questions |

### Presentation

These labels are **never shown to the user** directly. They are translated into plain language narrative:

Example: "There's strong evidence this works in other settings, but it's unclear whether the same mechanism applies in your context. The key uncertainty is whether [pathway step] would operate the same way in [user's setting]."

The score is presented as a hypothesis: "Based on available evidence and your stated context, this analysis has [level] confidence. [Binding constraint in plain language]. Is there anything you'd like to explore further or any questions about the assessment?"

---

## 8. Deep dive output format

The deep dive output uses Cartwright's framing as headings. The specific intervention design and outcome appear in the title.

### Structure

**Title:** "[Intervention design] for [outcome]"
e.g., "Tiered sugar levies for industry reformulation"

**Theory (headline):**
> This intervention works by [action], through [mediating process], if [key condition] is present.

**It worked somewhere**
2-3 sentences. Study count, dominant study designs, effect direction, causality claim. Cite sources with [N].

Scoring working shown in italics:
*Direction: [value] -> [result]. Evidence score: [value] -> ceiling [level]. Causality: [value] -> [modifier] -> [level].*

**It plays the same causal role here and there**
State the transferable causal role in bold. Show the core pathway as a chain: step -> step -> step -> outcome. 2-3 sentences on pathway plausibility in the user's context.

Scoring working shown in italics:
*Role specificity: [assessment] -> [result]. Pathway: [assessment] -> [result]. Context: [assessment] -> [result].*

**The support factors are here**
"Not yet assessed — let's check whether all the support factors are present."
Factor table with status, basis columns. Then enter factor resolution loop.

### Final assessment (after factor resolution)

Title: **"Final assessment — [Intervention design] for [outcome]"**

Repeats the theory headline, then shows all three Cartwright headings with their confidence levels, the completed factor table, and the overall score with binding constraint in plain language. Score presented as hypothesis: "Based on available evidence and your stated context, this analysis has [level] confidence. [Explanation]. Is there anything you'd like to explore further or any questions about the assessment?"

---

## 9. Cross-intervention comparison

When a user has deep-dived multiple interventions, comparison is presented as a side-by-side table. Column headers use the specific intervention design names (not the theme).

| | [Intervention design A] for [outcome] | [Intervention design B] for [outcome] |
|---|---|---|
| **It worked somewhere** | [level] | [level] |
| **Same causal role here and there** | [level] | [level] |
| **Support factors are here** | [status] | [status] |
| **Overall** | [level] | [level] |
| **Key constraint** | [plain language] | [plain language] |

No LLM-generated narrative synthesis — the table lets the user make their own judgment.

---

## 10. Critic pass design

A single expanded critic pass covers Legs 2 and 3 (Leg 1 is deterministic, no critic needed).

The critic reviews:
1. **Mechanism confidence**: Is the claimed confidence justified by evidence quotes?
2. **Role specificity**: Is the transferable causal role vacuous? (LLM-as-judge for abstraction level)
3. **Pathway plausibility**: Are any pathway steps implausible given the evidence?
4. **Support factor quality**: Are any factors generic study-design features rather than transferability-relevant?
5. **Missing dealbreakers**: Given user context, are there obvious conflicts the extraction missed?
6. **Quote verification**: Do quoted passages actually appear in the raw evidence?

Critic can only maintain or downgrade confidence levels, never upgrade.


---

## 11. Open questions

1. **Cluster identification quality**: The reconciliation LLM needs to reliably distinguish "same intervention described differently" from "genuinely different intervention designs." Need to test with real data to see how often false splits or false merges occur.

2. **Per-study extraction feasibility**: The 30s latency budget for per-study extraction assumes concurrent LLM calls for 3-15 documents. Need to benchmark actual latency and determine if batching or other optimisation is needed as this could keep policymaker waiting for too long.

3. **Structured UI for outcome selection and cluster selection**: Frontend implementation needed for both the outcome card/dropdown and the cluster selection step. Design mockups should show how these integrate with the existing chat sidebar.

4. **Leg 1 computation at cluster level**: When Leg 1 is computed for a cluster of 2-3 studies, the effect direction, evidence score, and causality claim need to be aggregated from per-document metadata. Need to verify that per-document `effect_direction` and `causality_claim` are available for the specific outcome (not just document-level aggregates).

---

## 12. Relationship to current PR #153

PR #153 is a working prototype that validates the three-leg conversational flow. This spec describes the systematic version. Key differences:

| Dimension | PR #153 (current) | This spec |
|-----------|-------------------|-----------|
| Unit of analysis | Intervention theme | Theme x outcome x intervention cluster |
| Leg 1 scoring | LLM-narrative, non-deterministic | Deterministic algorithm from metadata, scoped to cluster |
| Leg 2 extraction | Theme-level, single prompt | Per-study, reconciled to cluster with cluster identification |
| Leg 2 abstraction | Programme theory sentence | Explicit transferable causal role + core pathway |
| Leg 3 factors | Direct extraction only | Two-pass (direct + pre-mortem) + pathway decomposition |
| Factor status | Present/Absent/Buildable/Unknown | Present/Buildable/Absent/Unknown |
| Outcome narrowing | No (theme-level assessment) | Yes (structured UI, user picks outcome) |
| Cluster identification | No | Yes (emerges from reconciliation, user picks design) |
| Score reproducibility | No (LLM-dependent) | Leg 1 deterministic; Legs 2-3 structured |
| User-facing headings | Outcome/Mechanism/Context | Cartwright framing (It worked somewhere / Same role / Support factors) |
| Comparison | LLM narrative | Side-by-side table with Cartwright headings |
| Scoring transparency | Hidden | Scoring working shown in italics |

PR #153 remains valuable as the conversational UX layer. This spec primarily changes what happens **inside** the deep dive (extraction quality, scoring rigour, unit of analysis) while preserving the user-facing flow and adding the outcome selection and cluster identification steps.
