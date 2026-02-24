# Spec: Refine Search Onboarding Tutorial

## Problem

When users click "Refine & re-search" on a completed project and land on the wizard Summary page, two things are unclear:

1. **Navigation**: The numbered step circles in the progress bar are clickable and allow jumping to any wizard step to edit parameters — but this isn't obvious.
2. **Purpose**: Users don't immediately understand what they can do on the Summary page or how to proceed.

This is a first-time discoverability problem. Once a user understands the flow, it's intuitive — so the solution should teach once and get out of the way.

## Solution

A spotlight/coach-mark tutorial that triggers the first time a user enters the wizard via "Refine & re-search". The tutorial is entirely self-contained on the `/search` wizard page (no cross-page state). It consists of an opt-in intro prompt followed by a 3-step guided spotlight tour.

## User Flow

### Trigger

1. User is on a project Results page with a completed or failed project.
2. User opens "View search settings" modal and clicks "Refine & re-search".
3. User is navigated to `/search`, where the wizard opens at the Summary step with all previous search parameters pre-loaded.
4. On mount, the wizard checks two conditions:
   - `parentProjectId` in the wizard store is non-null (i.e. this is a refine, not a fresh search).
   - `localStorage.getItem('refine_tutorial_seen')` is falsy.
5. If both conditions are met, the intro prompt appears.

### Intro Prompt

A centered dialog (using the existing `Dialog` component from `@/components/ui/dialog`) overlaid on the wizard page:

- **Title**: "First time refining a search?"
- **Body**: "Take a quick 3-step tour to learn how to tweak your search settings and re-run."
- **Buttons**: `[Show me]` (primary) `[No thanks]` (secondary/ghost)

If the user clicks **"No thanks"**:
- Set `localStorage.setItem('refine_tutorial_seen', 'true')`.
- Dismiss the dialog. User proceeds normally.

If the user clicks **"Show me"**:
- Dismiss the dialog and begin the spotlight tour.

### Spotlight Tour

Three sequential steps, each consisting of:
- A dark semi-transparent overlay covering the entire page.
- A spotlight cutout (via CSS `clip-path` or mask) around the target element.
- A Radix `Popover` tooltip positioned near the spotlight, containing:
  - Step counter: "Step 1 of 3", "Step 2 of 3", "Step 3 of 3"
  - Instructional text (see below)
  - **Next** button (or **Done** on the final step)
  - **Skip tutorial** text button

#### Step 1 of 3 — Progress Bar

- **Target element**: The progress bar (step circles 1–7) at the top of the wizard.
- **Tooltip text**: "Your previous search settings are pre-loaded. Click any step above to jump there and make changes."
- **Tooltip position**: Below the progress bar.
- **Tone**: Contextual — explains the situation before being instructional.

#### Step 2 of 3 — Filters Summary Section

- **Target element**: The Filters summary card on the Summary page (contains sources, retrieval limit, time window, geography).
- **Auto-scroll**: If the Filters section is not fully in the viewport, smooth-scroll it into view before showing the spotlight.
- **Tooltip text**: "Click any section to edit it directly — try narrowing your geography or time window."
- **Tooltip position**: To the right of the section (or below on narrow viewports).
- **Tone**: Instructional with a concrete suggestion.

#### Step 3 of 3 — Run Button

- **Target element**: The "Run search" button at the bottom of the Summary page.
- **Auto-scroll**: Smooth-scroll the button into view if needed.
- **Tooltip text**: "When you're happy with your changes, hit Run to start a new search."
- **Tooltip position**: Above the button.
- **Tone**: Direct and instructional.

### Early Completion

If at any point during steps 1 or 2 the user clicks the **highlighted target element itself** (e.g. clicks a step circle to navigate, or clicks the Filters section), the tutorial is immediately marked as complete:
- Set `localStorage.setItem('refine_tutorial_seen', 'true')`.
- Remove the overlay.
- Let the user's click action proceed normally.

Rationale: clicking the highlighted element demonstrates the user understood the instruction — no need to continue.

### Completion / Skip

On completing the final step or clicking "Skip tutorial" at any step:
- Set `localStorage.setItem('refine_tutorial_seen', 'true')`.
- Remove the overlay and all tooltips.

The tutorial will not appear again for this browser.

## Persistence

- **Mechanism**: `localStorage` key `refine_tutorial_seen`.
- **Scope**: Per-browser. If the user switches browsers or clears storage, they may see the tutorial again. This is acceptable — the tutorial is brief and non-disruptive.
- **No server-side storage**: Avoids a DB migration and API endpoint for a low-stakes preference.

## Technical Implementation

### State Management

- **No new Zustand store**. Use React component state (`useState`) within the tutorial component:
  - `tutorialStep: 'intro' | 1 | 2 | 3 | null` — current active step, or `null` when not running.
- **Trigger detection**: Read `parentProjectId` from `useWizard` store on mount. Check `localStorage` for the seen flag.

### Component Structure

```
frontend/components/search/
  RefineTutorial.tsx        # New component — self-contained tutorial logic + UI
```

**`RefineTutorial`** is rendered inside `SearchWizard` and receives no props (reads wizard store directly). It manages its own state and renders:

1. The intro `Dialog` (when `tutorialStep === 'intro'`).
2. The spotlight overlay + `Popover` tooltip (when `tutorialStep` is 1, 2, or 3).

### Spotlight Overlay

- A full-screen fixed `div` with `z-index` above page content but below the tooltip.
- Background: `rgba(0, 0, 0, 0.5)` (semi-transparent black).
- Cutout: Use CSS `clip-path: path(...)` or a CSS mask with an inverted rounded rectangle to create the spotlight hole around the target element.
- Target element position: Obtained via `ref` or `document.querySelector` + `getBoundingClientRect()`. Recalculate on window resize.

### Tooltip

- Use Radix `Popover` (already available via `@/components/ui`) for positioning and portal rendering.
- Anchor the popover to the target element's bounding rect.
- **Focus trap**: Trap keyboard focus within the tooltip (Tab cycles through Next/Skip buttons only). Use Radix's built-in focus management or a `FocusTrap` wrapper.

### Auto-Scroll

Before showing steps 2 and 3, call `element.scrollIntoView({ behavior: 'smooth', block: 'center' })` on the target element. Wait for scroll to complete (use a short `setTimeout` or `IntersectionObserver`) before displaying the spotlight.

### Target Element References

Each spotlight step needs to locate its target DOM element. Use `data-tutorial` attributes on the relevant elements:

- Progress bar container: `data-tutorial="progress-bar"`
- Filters summary section: `data-tutorial="filters-section"`
- Run button: `data-tutorial="run-button"`

The tutorial component queries these with `document.querySelector('[data-tutorial="..."]')`.

## Edge Cases

| Scenario | Behaviour |
|---|---|
| User resizes window during tutorial | Recalculate spotlight position on `resize` event |
| Target element not found in DOM | Skip that step silently, proceed to next |
| User navigates away mid-tutorial | Tutorial state resets (component unmounts). If they didn't complete it, the flag is not set — they'll see it again next time. |
| User refreshes mid-tutorial | Wizard store resets (parentProjectId is null), so the tutorial won't re-trigger. The seen flag is not set, so they'll see it on their next refine. |
| localStorage is unavailable (private browsing) | Tutorial shows every time. Acceptable — wrap localStorage access in try/catch. |

## Acceptance Criteria

- [ ] Tutorial intro prompt appears the first time a user lands on the wizard via "Refine & re-search".
- [ ] Tutorial does NOT appear on fresh searches (parentProjectId is null).
- [ ] Tutorial does NOT appear if the user has previously completed or skipped it.
- [ ] All 3 spotlight steps display correctly with proper positioning and auto-scroll.
- [ ] Step counter shows "Step X of 3" on each tooltip.
- [ ] "Skip tutorial" is available on every step.
- [ ] Clicking a highlighted element during steps 1-2 marks the tutorial as complete.
- [ ] Keyboard focus is trapped within the tooltip during the tour.
- [ ] Overlay and tooltips are fully removed on completion/skip.
- [ ] No visual glitches on resize or scroll during the tour.

## Out of Scope

- Server-side persistence of tutorial state.
- Tutorials for other features (this spec covers only the refine search tutorial).
- Replay mechanism (no "?" icon to re-trigger the tutorial). Can be added later if needed.
- Mobile/responsive layout (the wizard is primarily a desktop experience).
