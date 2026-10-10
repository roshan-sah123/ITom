# Internal buyer review: location scorecards

10 October 2026. Audience: operations team and leadership. Source: the running portal, current code and database-backed APIs, plus the existing agreed location-score scope. No new business thresholds were inferred from competitors or presented as industry standards.

## Buyer verdict

Suitable for a controlled internal pilot, with clearer decisions and corrected score-integrity failure paths. **Engineering readiness judgment: 78/100**, improved from the previous 65/100 review after addressing its two P1 defects. This is not measured data accuracy or a probability that a physical location is correct. Broad production approval still needs the remaining lifecycle, scale and PostgreSQL checks below.

The useful buying outcome is: identify a reporting group requiring attention, understand the reason and evidence, open exactly the affected source records, and export the selection. A global blended score, office count, business impact rating or SLA would overstate the current evidence, so none was added.

## Observed flow and changes

1. **Enter Location Health — improved.** The original 84 headline looked like a count of offices. It now explicitly says populated reporting groups, with mixed levels disclosed. Source success times and assignment coverage are visible. Screenshot 01 shows the original entry; 03 shows the revised summary.
2. **Choose a group or issue — improved.** The original view had no concise fleet-level status summary and rendered every group. Clickable Red, Warning, Insufficient data and Green counts now respect search, level and score mode. Cards show specific low components, supporting counts and source scope. Unassigned records are a separate coverage task. Twenty-four cards load initially; Show more expands the view. Screenshot 04 shows the refined cards.
3. **Investigate and return — improved.** The original issue click scrolled below the complete catalogue and used space for mostly empty raw source locations. Inventory now replaces the catalogue, keeps source/issue/search/export controls, shows status badges and last Intune check-in age, and offers Back to locations. Back restores filters/focus; Refresh preserves filters. Raw source location remains available in the device drawer and export. Screenshots 02 and 05 show before/after inventory.

## Current audit evidence

![Original cards](../outputs/location-product-review/01-before-cards.png)

![Original inventory](../outputs/location-product-review/02-before-inventory.png)

![Refined summary](../outputs/location-product-review/03-after-summary.png)

![Refined cards](../outputs/location-product-review/04-after-cards.png)

![Refined inventory](../outputs/location-product-review/05-after-inventory.png)

![Responsive summary at 390px](../outputs/location-product-review/06-after-mobile.png)

Screenshots were captured in this review run using the in-app browser and inspected before acceptance. Live counts are observations, not fixed expected baselines.

## Score and trust decisions

- Preserve policy location-v1, its weights, 75/90 operating bands and 95% field-coverage gate. These remain provisional until operations approves targets.
- Keep source modes explicit. Status counts summarize groups under the selected mode; they do not average unlike endpoint/infrastructure/combined scores. Country, city, office and cloud groups remain distinguishable by level.
- Keep missing/stale required data grey. No source records, unmanaged-only groups, insufficient field coverage and identity review have readable explanations. Never turn a missing source into a healthy zero.
- Do not sum issue chips as unique affected devices: noncompliance and old check-ins can overlap. Counts remain source records rather than deduplicated physical assets.
- An operational score is not service uptime, business criticality or an SLA. There is no service ownership/impact evidence to justify critical-business-site overrides or a ticket workflow.
- Do not assert that an assigned location proves physical presence. The user-supplied workbook remains bootstrap knowledge; runtime ownership stays in the database.

## Integrity fixes included

**Failed-history atomicity:** A regression first reproduced committed CI changes despite a failed source audit. Inventory updates, retirement, source-success fields and score observations now share one savepoint. A history failure rolls them back and persists FAILED with zero committed update/retirement counters. The regression includes a changed existing CI, a retired CI and partially written observations.

**Read coherence:** Reader/writer regressions first reproduced old Compliant counts combined with a newer successful source timestamp. Scores now compare source-run, inventory-update and mapping/location markers before and after reading inputs, and retry if they differ. Both catalogue and individual scores are covered. Location metadata is read as fresh SQL values, avoiding an old ORM identity after a rename. Three consecutive changes return HTTP 503. This relies on supported application writers; arbitrary direct SQL edits outside their contracts remain outside the guarantee.

## Validation

- Default suite: 291 passed, four existing strict expected failures, 41 subtests passed.
- Eighteen location contracts include six new rollback/concurrency/retry regressions.
- Four isolated browser journeys cover the operator queue plus refined cards, semantic badges, source/issue filters, unassigned review, check-in ages, CSV selection, back navigation, refresh preservation, progressive display and 390px layout.
- Browser navigation tests use the real application/API/database and stub only unrelated third-party chart/font downloads. In-app verification uses the running portal assets and actual source mirrors.
- The live 390px content viewport showed a two-column summary and stacked filters without document overflow. Desktop viewport settings were restored after capture. Two temporary source-health fetch errors occurred during the planned local-server restart; the portal subsequently loaded current scores and exact issue rows successfully.
- Focus styling, labelled controls, table headers/caption, retained status text, detail-heading focus and return focus improve accessibility. The screenshots and browser checks do not establish full WCAG compliance or screen-reader conformance.

## Remaining limits and next operating decisions

The previous review's P2 concerns remain: free-text notes influence mapping review state; the rule-import workflow still derives identities from display names and lacks immutable revision content; device filtering/pagination/export materializes records in memory; history needs an agreed retention policy. Progressive card display reduces browser clutter, not backend scan cost. No historical rows were deleted.

PostgreSQL concurrency/deployment and representative multi-user performance still need verification. Application-wide authentication concerns from the earlier codebase audit are outside this scorecard refinement. Physical location accuracy requires source owners to validate ambiguous groups, including duplicate-looking names, before leadership treats them as real sites.

Before broad rollout, agree the operating bands, designate a location-data owner, validate ambiguous groups, and choose history retention. These are business decisions; the portal should not invent them.
