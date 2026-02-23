# Spec: Refine & Re-search

## Problem

Users who complete a search want to tweak parameters (e.g. narrow population, change geography) without re-entering everything from scratch. Currently the only option is "Start new search" which resets all fields.

> "I just wanted to tweak a couple of things in my original search criteria and then for it to run the search again." — Piloter feedback

## Design Decision

**Prefill the existing search wizard** rather than making the Search Settings modal editable.

Rationale:
- The wizard steps (Question, Population, Setting, Outcome, Refinement, Filters, Summary) map directly to the user-controllable inputs.
- The Search Settings modal also shows AI-generated outputs (semantic query, boolean queries) that aren't meaningful to edit.
- The wizard stepper supports clicking steps to jump — so a user refining geography can jump straight to Filters, tweak, and submit from Summary.
- Creates a new project each time, preserving the original results.

## User Flow

1. User is on the project results page (`/projects/{projectId}`).
2. Clicks **"View search settings"** — Search Settings modal opens.
3. At the bottom of the modal, clicks **"Refine & re-search"** (replaces the current "Start new search" button).
4. This populates the `useWizard` store with the current project's `search_query` values, closes the modal, and navigates to `/search`.
5. The wizard opens at the **Summary** step so the user sees all their previous parameters at a glance.
6. All stepper steps are clickable — user jumps directly to whichever step they want to change.
7. After tweaking, user jumps back to Summary (via stepper) and clicks "Run search" — creates a new project with `(refined)` appended to the title.

## Decisions

| Topic | Decision | Rationale |
|---|---|---|
| Project lineage | Store `parent_project_id` FK on new project | Enables future features (compare, history tree) |
| Research question change | Keep existing selections | Optimise for the common case (minor tweaks). User updates stale selections manually. |
| Step navigation | Direct jump both ways | Click any step from Summary, make change, click Summary to jump back. Fastest iteration. |
| Entry point | Replace "Start new search" in modal | Single entry point. "Start new search" is still available via the Search nav link. |
| Project status | Completed + failed | Failed searches are a strong motivator to tweak and retry. `search_query` is saved for both. |
| State persistence | Accept loss on refresh | Flow is a single client-side navigation. Manual refresh is rare; user can click Refine again. |
| Lineage UI | "Refined from: {title}" link on child | Lightweight context on the refined project's results page. |
| Wizard appearance | No distinction from normal wizard | Prefilled values are self-evident. No banners or heading changes. |
| Sub-questions | Skip ADDITIONAL_QUESTIONS step | Same as today. Don't change wizard step flow for this feature. |
| Project naming | Always append `(refined)` | No version counting. "Refined from" link distinguishes multiple refinements. |

## Technical Changes

### 1. DB: Add `parent_project_id` column

**Migration:** `backend/supabase/migrations/YYYYMMDD_add_parent_project_id.sql`

```sql
ALTER TABLE analysis_projects
  ADD COLUMN IF NOT EXISTS parent_project_id UUID DEFAULT NULL
  REFERENCES analysis_projects(id) ON DELETE SET NULL;
```

`ON DELETE SET NULL` so deleting the parent doesn't cascade-delete refined projects.

### 2. Backend: Accept `parent_project_id` on project creation

**File:** `backend/app/api/projects.py`

Add `parent_project_id: Optional[str] = None` to the create-project request schema. Pass it through to the DB insert.

Add `parent_project_id` to the project response schema so the frontend can read it.

### 3. `useWizard` store: Add `initFromSearchQuery()` method

**File:** `frontend/components/search/SearchWizard.tsx` (~line 163)

Add a new action:

```typescript
initFromSearchQuery: (sq: AnalysisProject['search_query']) => void;
```

Field mapping from `search_query` to wizard state:

| `search_query` field | Wizard state field |
|---|---|
| `research_question` | `researchQuestion` |
| `population` | `population.selected` (`noPreference: true` if empty) |
| `inner_setting` | `innerSetting.selected` (`noPreference: true` if empty) |
| `outcome` | `outcome.selected` (`noPreference: true` if empty) |
| `screening_factors` | `screeningFactors` |
| `implementation_constraints` | `implementationConstraints` (capitalise first letter of values) |
| `sources` | `parameters.sources` |
| `geography_filter` | `parameters.geography` |
| `time_preset` | `parameters.timePreset` |
| `time_from` / `time_to` | `parameters.customFrom` / `parameters.customTo` |
| `limit` | `maxResults` |

Additional behaviour:
- Set `step` to `"SUMMARY"`.
- Set `allStepsVisited: true` (new boolean flag) so all stepper steps are clickable.
- Copy selected values into `generatedPopulationOptions`, `generatedInnerSettingOptions`, `generatedOutcomeOptions` so they display as selectable chips if the user navigates back to those steps.
- Fall back to defaults for any missing field (same defaults as `reset()`).

### 4. `useWizard` store: Add `allStepsVisited` flag

**File:** `frontend/components/search/SearchWizard.tsx`

New boolean in the store, default `false`. Set to `true` by `initFromSearchQuery()`. Reset to `false` by `reset()`.

Used in the `ProgressBar` component to make all steps clickable (both forward and backward jumps) when `true`.

### 5. `ProgressBar`: Allow forward jumps when `allStepsVisited`

**File:** `frontend/components/search/SearchWizard.tsx` (~line 267)

Currently the stepper only allows clicking back to previously visited steps. When `allStepsVisited` is `true`, allow clicking any step regardless of current position — including jumping forward to Summary from any step.

### 6. `SearchPlanModal`: Replace "Start new search" with "Refine & re-search"

**File:** `frontend/components/results/SearchPlanModal.tsx` (~line 121)

Replace the existing `startNewSearch` handler:

```typescript
const refineSearch = () => {
  useWizard.getState().initFromSearchQuery(project.search_query)
  setIsOpen(false)
  router.push('/search')
}
```

Update the button label from "Start new search" to "Refine & re-search".

Only show the button when project status is `completed` or `failed`.

### 7. Search page: Don't reset wizard if already initialised

**File:** `frontend/app/(main)/search/page.tsx`

Currently the search page may reset the wizard on mount. Add a guard: if `useWizard.getState().allStepsVisited` is `true`, skip the reset — the store was just populated by the refine flow.

### 8. Project creation: Pass `parent_project_id` and append title

**File:** `frontend/app/(main)/search/page.tsx` (in `handleRunAnalysis`)

When creating the project via `createAnalysisProject()`:
- If the wizard was initialised via `initFromSearchQuery()`, pass `parent_project_id` (store it alongside `allStepsVisited` in the wizard store).
- Append ` (refined)` to the project title.

### 9. Project results page: Show "Refined from" indicator

**File:** `frontend/app/(main)/projects/[projectId]/page.tsx`

If `project.parent_project_id` is set:
- Fetch the parent project title (may already be available in the projects list store).
- Display a subtle line near the project header: "Refined from: {parent title}" as a clickable link to `/projects/{parent_project_id}`.
- If the parent project was deleted (null from API), hide the indicator.

## Scope Boundaries

**In scope:**
- Prefilling wizard from existing `search_query`
- "Refine & re-search" button replacing "Start new search" in Search Settings modal
- Direct jump navigation in wizard when refining
- `parent_project_id` DB column and API support
- "(refined)" title suffix
- "Refined from" link on child project

**Out of scope (future):**
- Editing search parameters in-place within the modal
- "Refined into" indicator on parent project (reverse direction)
- Refine action in the project list view
- Version numbering for multiple refinements
- State persistence across page refresh
- Surfacing ADDITIONAL_QUESTIONS / sub-questions step
- Comparing results between original and refined searches

## Edge Cases

- **Missing fields in legacy `search_query`:** `initFromSearchQuery()` falls back to defaults for any missing field.
- **LLM-generated options:** Pre-selected values show as chips. If the user changes the research question (step 1), existing Population/Setting/Outcome selections are kept. New LLM options are not regenerated unless the user triggers it.
- **Deleted parent project:** "Refined from" indicator is hidden if parent no longer exists (`ON DELETE SET NULL`).
- **Failed project with partial `search_query`:** The `search_query` is stored at run initiation, so it should be complete even for failed projects. Any missing fields fall back to defaults.
- **Browser refresh:** Wizard state is lost. User sees an empty wizard and can navigate back to the project to click Refine again.
