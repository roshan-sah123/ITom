# Frontend polish plan — 11 October 2026

> Historical planning record. Tasks 1–3 were completed at archive time; tasks
> 4–5 were not confirmed complete. Reassess them against the current portal and
> tests before creating new work. This file is not the active project backlog.

## Recommendation

Deliver focused improvements in this order: exception investigation, freshness, CMDB clarity, filter visibility, and recovery messages. Use the current HTML/CSS/JavaScript architecture and existing APIs. These are proposed changes, not implemented changes. The device detail fix is already complete.

## Findings from current source

- app.js navigates to the top of every workspace. Home exception actions already pass source-specific filters. Infrastructure and Endpoints put large chart grids before inventory. Improve the landing experience without changing query semantics.
- system/freshness supplies per-source synchronization time, age, status, and a configured freshness window. Reuse this definition rather than calculating new frontend thresholds. Source freshness and latest attempt outcome describe different things; show failed/partial attempts even when a prior snapshot exists.
- home.js's Refresh data rereads stored summaries; it does not trigger source ingestion. Name the action Reload snapshot. Replace Live Intune data and Live distribution with snapshot wording.
- The unique database identity is source_system + source_id. This prevents duplicates within a source, but does not establish cross-source deduplication. Describe totals as source records unless a separate identity-reconciliation capability is proven.
- cmdb.js calculates Health Compliance Baseline from high_health_count / total_cis. This is a normalized tier distribution, not a single source compliance measure. Prefer removing that combined KPI and retaining meaningful source-specific metrics in their own workspaces.
- The CMDB provenance markup has bar and segment classes without matching style rules found in the active stylesheet. Add scoped styles and test the rendered bar dimensions before considering the blank panel fixed.
- Filter state variables retain multiple constraints, while a single filter label is overwritten by the latest change. Users can see an incomplete account of what narrowed their results.
- Endpoint inventory failure copy says Upstream Graph API offline even though the browser reads the portal database API. Avoid inferring an external outage from a failed inventory request.

## Task 1: Land exception actions at relevant inventory

Scope: Medium. Likely files: app.js, infraWorkspace.js, endpoints.js, browser operator-queue tests.

Acceptance:
- Infrastructure and endpoint exception shortcuts apply the existing filter, then reveal and focus the inventory heading after it is ready.
- An optional chart summary can be expanded without losing filters or results; retain DOM reading order consistent with the visual layout.
- Reset, pagination, exports and detail drawers retain existing behavior at desktop and 390px widths.

Verification: Extend tests/browser/test_operator_queue.py to assert filtered count, landing focus, and visible inventory; inspect desktop and narrow screenshots. Handle reduced motion and avoid scrolling before asynchronous inventory finishes.

Dependencies: None. Use this as the next implementation slice.

## Task 2: Carry source evidence into workspaces

Scope: Medium. A shared freshness component, app.js, home.js, workspace markup and focused browser tests.

Acceptance:
- Infrastructure shows SolarWinds evidence; Endpoints shows Intune evidence; CMDB shows both separately.
- Distinguish fresh, stale, unknown, failed/partial latest attempt and failed freshness request; retain last successful synchronization time when supplied.
- Reload snapshot only performs reads. No source sync is triggered by navigation or reload.

Verification: Deterministic browser cases for mixed source freshness and freshness endpoint failure. Verify the existing backend threshold is reused, and older requests cannot overwrite a newer workspace.

Dependencies: None; follow Task 1 for a stable workspace heading placement.

Checkpoint after Tasks 1–2: verify overview → exception → filtered inventory → detail → close; snapshot age remains visible and no source-writing requests occur.

## Task 3: Correct CMDB accounting and source distribution

Scope: Medium. index.html, cmdb.js, style.css, focused CMDB browser tests.

Acceptance:
- Labels explicitly identify total source records, Microsoft Intune records and SolarWinds records.
- Remove the mixed Health Compliance Baseline or explicitly label it as a derived tier distribution with its definition; do not present it as endpoint compliance.
- Source totals reconcile with the displayed total; a visible, compact distribution bar has text equivalents and an explicit unavailable state.

Verification: Use seeded API totals and mismatched/unavailable summaries; assert labels, segment widths and bar height, then inspect screenshot. Keep the current backend accounting unchanged.

Dependencies: None.

## Task 4: Make all active filters visible

Scope: Medium. Infrastructure and Endpoints filter renderers, markup and focused browser tests. Apply CMDB separately if it exceeds five files.

Acceptance:
- Show every active constraint from actual filter state, including chart-applied OS/vendor filters; removing one chip preserves the others.
- Provide independent accessible names for search and filter controls. Report result counts through a concise status region.
- Endpoint filters provide investigation paths for supported reported compliance states, verified against persisted status values and API filtering.

Verification: Combine status + location + search, remove one constraint, and compare results/export with the remaining constraints. Confirm chart and dropdown filters agree; test grace-period/unknown states with seeded data before adding options.

Dependencies: Task 1's inventory heading.

## Task 5: Make recovery messages actionable

Scope: Small per workspace; ship separately.

Acceptance:
- Distinguish no matching results, no ingested dataset and failed inventory request.
- No-results offers Clear filters; request failure offers Retry with current filters preserved.
- Copy describes the known failure and does not claim Graph/SolarWinds is offline without source evidence.

Verification: Seed empty and failed responses; test recovery, retained filters and screen-reader status messages.

Dependencies: Task 4's filter state presentation.

## Research sources

- [Carbon data table guidelines](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines): supports table-centered search/filter/export controls, clear table titles and space for dense data. Applying this to exception landing is our product-specific recommendation.
- [PatternFly empty states](https://www.patternfly.org/components/empty-state/design-guidelines/): distinguishes no results from configuration problems and recommends a useful next action.
- [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html): loading, result counts and errors should be exposed to assistive technology without unnecessary focus changes.

## Boundaries and unknowns

This is a short source review plus authoritative design research, not a new browser audit or user study. No production code changed in this research pass. Expected benefits are hypotheses; validate time/clicks to reach a matching device and task completion before/after implementation. No numeric performance improvement is promised.

Avoid a framework migration, new ingestion fields, topology, automated remediation and cross-source physical-device matching in this polish batch. Policy failure reasons require new evidence if not already fetched. Broader URL deep linking and saved searches can follow after these core flows work consistently.
