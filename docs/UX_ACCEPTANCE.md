# UX design specification and acceptance

Documentation-only proposal at `e95047e`. Fields/formulas: [dictionary](UI_DATA_DICTIONARY.md); current inventory/evidence: [R&D](FRONTEND_RND.md). Implementation requires approval of a specific ticket. Keep existing view targets, standalone URLs, APIs, vanilla JS/shared CSS, SQLite, integrations, exports and drill-downs. No new backend/security/scheduler/deployment logic is authorized by this document.

## Current → proposed hierarchy

| Current navigation | Proposed destination and retained capability |
| --- | --- |
| Overview | Operations Overview: attention and evidence summary |
| Infrastructure → servers/networks/sites/baseline | Investigation → Infrastructure / Locations; retain all-node/network tables, canonical groups and the planned baseline destination |
| Endpoints | Investigation → Endpoints; retain compliance inventory, charts and storage evidence |
| CMDB | Asset Explorer → cross-source records/provenance, filtering, CSV, shared device detail |
| Footer Sync runs / Sync & schedule | Data Confidence → source freshness, attempts, schedule and ledger; retain current target IDs |
| Location review entry within Sites | Data Confidence → Location assignment, with location investigation backlink; retain restricted review capability |
| Knowledge / Automations / Zero Trust / Baseline | Supporting/planned content outside the main decision path; keep reachable links and explicit unavailable status |
| Standalone CMDB / infrastructure analytics | Retain compatibility URLs, make evidence truthful, then align approved components incrementally; no silent redirects/deletion |
| TechAdmin external link | Remains external, separate ownership and behavior |

This is an information hierarchy, not a request to create new API routes or replace all components. Inventory composition and history/planning remain secondary sections within Investigation/Explorer, not additional headline health KPIs.

## Screen wireframes

**A. Operations Overview — VP/NOC.** Header: title, stored-snapshot scope, source warning, GET-only reload. First row: three existing O4/O5/O6 KPIs, each with numerator/denominator, coverage and last-success evidence. Second row: separate operational exception categories with matching investigation links; beside them, concise confidence warnings. Small source-record counts below, not competing headline tiles. Expandable definitions. No combined health or business-impact score.

**B. Investigation — NOC/operator.** Header: source scope and loaded snapshot evidence. Tabs: Infrastructure, Endpoints, Locations. Start with relevant exception counts; then active-filter summary, controls and table; collapsed composition charts below/alongside. Infrastructure separates operational status, derived tier and measured resource pressure. Endpoints separates compliance from check-in/storage. Locations starts with explicit mode/level, component ratios, coverage, issue links and Unassigned; weighted score is expandable supporting evidence. Source-scope filtering does not silently change calculation. Keep all existing subviews reachable.

**C. Asset Explorer — operator.** Compact source-record/provenance counts; search and source/health/raw-location filters; visible active filters/reset/result count; paginated table and all-filter CSV. Selecting a device opens the existing drawer with identifiers, source, status, health definition, mirror time, recorded attributes and history. Use canonical assignment IDs/resolution only when returned; don't invent canonical names. Preserve the original row and filters on close. Existing source-specific inventories remain available.

**D. Data Confidence — all roles/operator detail.** Per-source rows: last successful completion, age/state, latest attempt/outcome, coverage warnings. Assignment section: per-source mapped/unassigned counts and restricted review queue/history. Collection section: actual configured interval, scheduler process state, next run, existing explicit sync action and run ledger. Snapshot reload and ingestion must be distinct. No new authorization policy or automated sync is introduced. History/planning is labeled observation/estimate, not continuous telemetry.

## Acceptance catalogue

All data is synthetic in isolated tests, never operational fixtures. Browser tests must block source HTTP and replace manual-sync/review writes with spies/mocks. Read-only documentation validation does not execute these proposed journeys.

| ID | Acceptance requirement and proposed regression |
| --- | --- |
| A01 Evidence states | For each KPI/chart/table use available nonzero, genuine zero, zero denominator, missing/null, empty distribution, HTTP failure, stale success and failed latest attempt. No healthy substitute, fabricated population or provisional percent; unaffected sources remain usable. |
| A02 Population | O4 includes unknown endpoints; O5 excludes only explicit Unmanaged; O6 shows its own all-node denominator and both-reading coverage. Component sums/distributions reconcile to stated scope. Never sum overlapping exceptions or infer unique assets. |
| A03 First search | Fresh load on Overview; delay CMDB summary/grid; enter search once. Exactly that query lands visibly in CMDB and its request, without first visiting CMDB. Subsequent searches work; empty search follows existing behavior. No live API calls. |
| A04 Request ordering | For each grid, resolve two filter/search/page requests in reverse order. Rows, selected item mapping, totals and pagination must describe only the newest scope. Navigation away/back, refresh and drawer close must invalidate old responses. |
| A05 Chart journeys | Each category click has an equivalent keyboard control and produces the stated population. Raw SolarWinds Unknown, Unmanaged and Shutdown remain distinct where displayed. OS selection using general search must be labeled search, not exact OS filtering. Charts have a readable count/denominator alternative. |
| A06 Filters | Active filter summary includes every applied scope (including chart-set vendor/status); reset removes all of them; changed filter resets page. Dropdown values represent chart-selected states or show an explicit equivalent control. Preserve source, health, status, type and raw-location semantics; don't introduce unsupported environment/date facets. |
| A07 Export | Main grids export every matching API page with the same filter parameters; no silent first-page cap. Test 0, >100 rows, quoting/newlines/formula-like strings, failures and total changes. Snapshot consistency must not be claimed from equal counts alone. Legacy export label/behavior must agree. Location export keeps source/issue/search plus record count/as-of and states backend limits honestly. |
| A08 Device detail | Open from nodes/network/endpoints/CMDB/location list; resolve correct CI id; show escaped optional fields, unknowns and mirror time. No data after close/selection change. History failure leaves current detail intact; empty history does not imply no incidents. Preserve focus trap, Escape, background inertness and focus return. |
| A09 Location components | Verify exact C/R/H formulas, 95% coverage boundary, 7/30-day boundaries, invalid future dates and rounded score boundaries. Preserve unavailable for stale/missing required source, zero population, review/conflict and Unassigned. Any required component below 75 or infrastructure Down/Critical must retain existing warning policy. |
| A10 Comparable locations | Comparison requires same score mode, source scope and reporting level, with policy/mapping/as-of context. Auto/mixed-level browsing remains possible but is not presented as a comparable ranking. Card issue counts reconcile with corresponding LD filtered totals. >30-day check-ins are a subset of >7-day, not additive. |
| A11 Assignment review | Preserve queue filters/page counts, global enabled-rule counts, legacy reviewer/date absence, read-only mode and history. In browser fixtures only, mock successful save, 403, 409, 422 and ambiguous failure; don't imply save succeeded on request acceptance. No actual writes during R&D. |
| A12 Time/confidence | Show F last-success separately from Y latest completion/attempt and CI/device timestamps. Age loaded evidence without claiming it refreshed. Summary-cache fallback retains original time; a newer header poll must not relabel old table contents fresh. Test all sources unavailable, one source failing and one source never confirmed. |
| A13 Unsupported surfaces | Initial HTML and later API responses must contain no static operational count, SLA, backup-key coverage or incident trend presented as measured. Empty T remains explicitly unavailable. Existing standalone routes return useful truthful content; no assumption they are unused. |
| A14 Planning/composition | Moving vendor/OS diversity/forecast panels preserves data and links. Forecast retains observed-day count/window, horizon/method and notice; fewer than seven daily observations remains unavailable. No OS-modernization or capacity-risk score inferred. |
| A15 Collection controls | Existing explicit manual-sync action remains distinguishable from GET snapshot reload. Mock request acceptance, rejection and failure; 202 is not completed ingestion. No frontend-only permission claim. Backend authorization remains a separate prerequisite for shared exposure. |
| A16 Responsive and keyboard | At 1440, 1024, 768 and 375 CSS px (plus 320 px reflow), readable KPI order and filters; no page-level horizontal scroll, tables may have labeled scroll regions. Drawer fits viewport; filters/CSV/reset remain reachable. Tab/Shift+Tab/Enter/Space work; `/` never steals input/textarea/contenteditable typing or modified shortcuts. |
| A17 Accessibility | Target WCAG 2.2 AA: semantic headings/landmarks, labels, table captions/headers, visible unobscured focus, non-color status labels, ≥4.5:1 normal-text and ≥3:1 UI contrast, ≥24×24 CSS px targets (prefer 44), zoom/reflow and reduced motion. Announce loading/error/result updates without noisy polling. Canvas content needs an equivalent text/table interaction. No compliance claim until browser/manual testing. |

## Independent implementation order

Each ticket is independently reviewable; do not combine the frontend reorganization with backend security, SQLite concurrency, SQL pagination or scheduler work. Scope changes require a new ticket. Preserve functionality rather than deleting served code.

| Order / priority | Ticket / bounded change | Evidence and validation gate |
| --- | --- | --- |
| 1 / P0 | **Truthful legacy CMDB summary and freshness.** Fix only initial/static summary claims and summary/freshness rendering on the served CMDB page; use actual C/F/Y fields. No export redesign or route removal. | X1, dictionary C/F/Y; A01/A02/A12/A13. See exact ticket below. |
| 1b / P0 | **Truthful legacy CMDB row defaults.** Show missing source/status/tier/time as missing rather than Intune/Active/High/Live Sync; retain table structure, filters and export. | X2; A01/A08/A13. Separate from summary changes and export work. |
| 2 / P0 | **Truthful standalone infrastructure unavailable states.** Remove measured-looking constants/unsupported SLA/security/facility claims; clearly mark unbound panels and controls unavailable. Preserve URL/content access and F/B updates. | X3–X5, T; A01/A13. Do not implement historical collection or silently redirect. |
| 3 / P1 | **Reliable first-use global search.** Coordinate listener readiness and navigation; preserve current search API semantics. | O10/C3; A03; delayed fixture regression before code. |
| 4 / P1 | **Latest-request wins in CMDB.** Add scoped request guard without changing filters/API. Other grids receive independent follow-up tickets using the same acceptance. | C3; A04/A06. Avoid a broad router rewrite. |
| 5 / P1 | **Faithful SolarWinds status distribution.** Plot actual raw states with exact supported status-filter landings; preserve Up decision KPI. | S9; A02/A05/A06. Unknown/Unmanaged/Shutdown fixtures required. |
| 6 / P1 | **Explicit location comparison mode.** Gate comparison on same scope/level; component-first evidence, retaining browsing, formulas and weighted scores. | L2/L3/L5; A09/A10. No changed score formula or mapping logic. |
| 7 / P1 | **Consistent loaded-snapshot evidence.** Align header/workspace/schedule/ledger labels and missing-value handling using existing F/Y/K/R fields. Separate small null-storage guard ticket for E7. | O9/D1/D2/E7; A01/A12. No new backend timestamps or freshness calculation. |
| 8 / P1 | **Chart-search and export clarity.** Split by component: OS search wording/control, legacy filtered CSV completeness, then table filters/race fixes. Preserve each contract; no unsupported exact facets. | E4/X2/E10/S14/S15; A04–A07. One component per patch. |
| 9 / P2 | **Progressive navigation and composition placement.** One destination per ticket: expose Data Confidence; move planning/composition; de-emphasize planned modules while retaining links. | Page map/S7/E3/E8/X7; A14–A16. Do not rebuild the shell. |
| 10 / P2 | **Keyboard/chart accessibility and CSS consistency.** First isolate slash-input fix, then chart text alternatives, then measured responsive/contrast repairs. Review duplicate helper/style consolidation only after consumer tests. | O10/X2/X5; A05/A08/A16/A17. Existing shared CSS and components remain the foundation. |

Manual-sync authorization is a separate P0 security dependency, not authorized as a frontend implementation ticket. No visual severity is asserted without rendering. Legacy static unsupported metrics are P0 because they violate the explicit evidence requirement, not because browser exploitability was demonstrated.

## Exact first implementation ticket

**Title:** Render truthful summary/freshness on `/cmdb_explorer.html`.

**Problem:** Initial HTML contains historical counts/percentages. Inline `initCmdb` substitutes constants using `||`, reads nonexistent `source_distribution`/`health_distribution`, and defaults missing sync state/age to healthy/one minute. C actually exposes category counts and `health_breakdown`; F is last-success evidence and Y is latest-attempt evidence. Calling all SolarWinds records servers and all High tiers compliance also conflates populations.

**Allowed files:** `frontend/cmdb_explorer.html`; focused assertions in `tests/test_ui_truthfulness.py`; new isolated browser test `tests/browser/test_legacy_cmdb_truthfulness.py`. If fetching F needs a reusable service method, a narrowly scoped addition in `frontend/js/services.js` and matching contract tests is allowed. Stop and split the ticket if module-loading repairs are required for the page to run; do not bundle helper migration.

**Implementation boundary:** Initial counts/widths/text are neutral until evidence. Use safe-integer nonnegative source counts and require Intune + classified servers + network + unclassified = total, as in current main CMDB. Label provenance as source records; don't rename all SolarWinds nodes servers. Use real health counts only as derived health tiers, not enterprise compliance; positive-denominator percentages only. Read F source timestamps/statuses and Y outcome independently. Retain all source/health/search/table/export/navigation behavior; do not invoke POST endpoints. This ticket does not fix row defaults or CSV scope (separate follow-ups).

**Tests before code:** Initial HTML has no measured-looking historical constants or widths; intercepted GETs exercise valid nonzero, actual zero, null/missing fields, inconsistent source counts, 503, one-source stale, latest failed attempt with earlier success, and unknown age/state. Assert no manufactured values, no division by zero, no failure-to-health fallback and no writes. Counts/widths derive from the same verified population. Other table/filter/export controls remain present and behaviorally unchanged.

**Existing coverage:** [truthfulness](../tests/test_ui_truthfulness.py), [zero-build](../tests/test_zero_build_compliance.py), [single-port](../tests/test_single_port_portal.py), [CMDB clarity](../tests/browser/test_cmdb_clarity.py), [freshness consistency](../tests/browser/test_freshness_consistency.py). Existing string checks alone do not validate runtime response keys or legacy script loading. Prefer `page.route` fixtures and no operational DB; no ingestion required.

**Done when:** focused static/browser tests pass in an available runner, zero/missing/stale journeys and keyboard/mobile compatibility are verified, and diff changes only this scope. If browser/dependencies are unavailable, report the missing validation and keep the change unverified for merge; no fabricated screenshots or pass claims.

## Validation boundary for this specification

Trace fields statically through existing frontend calls, route declarations, services/repositories and serializers; do not import/start the app for documentation checks. Check relative links, inventory coverage, contract field literals/formulas and documentation-only git diff. Existing dependency-free source contract functions may run directly and must be reported as such, not as pytest/browser validation. Browser capture, native mobile/accessibility behavior, production data coverage, external callers, CDN availability, gateway policy and actual deployment state remain unverified. No implementation, publication or PR until approval.

Documentation checks performed on 2026-10-16: 61 relative source/document links resolved; all 58 inventory IDs and 17 acceptance IDs were present exactly once; 239 registry field-token references were corroborated in backend source. Token matching supplements the producer trace, not runtime response validation. Thirteen existing functions from `test_ui_truthfulness.py`, `test_portal_navigation_contract.py`, `test_frontend_home_contract.py` and `test_endpoint_storage_panel.py` passed by direct invocation. Staged whitespace and documentation-only scope checks passed. No pytest, browser, app startup, integration request or database operation was run for this documentation task.
