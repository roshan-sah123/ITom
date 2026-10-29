# Location scorecards

Open **Infrastructure → Location Health**. The page uses database-owned locations and rules. The Excel workbook supplied the initial knowledge only; no spreadsheet is read during requests or syncs.

## What is implemented

- Stable location IDs, reporting levels, database source rules and per-device assignment provenance.
- Literal longest-prefix matching for Intune and normalized aliases for SolarWinds. Exact aliases take priority; a unique country-prefix/separator variant can reuse an existing rule without changing its approval state. Ambiguous aliases and country-unconfirmed targets are not selected through that fallback.
- More precise known locations are preferred when both source fields agree geographically. Conflicting cities/offices remain unassigned conflicts; generic country labels do not override a known office.
- Original source locations and device telemetry remain intact. CI details show canonical and raw location separately.
- Mapping revisions include the resolver version. Every future ingestion batch resolves assignments, including unchanged-health records.
- Source-specific and Combined scorecards, search/status/mode/level filters, exact issue drilldowns, paging, CSV exports and reset controls.
- Clickable red/warning/insufficient-data/green summary counts scoped to the current search, level and score mode. The populated reporting-group count excludes empty groups and Unassigned; it is not a physical-office count.
- A separate unassigned coverage task, 24 cards initially with progressive disclosure, source scope on each card, specific low-component explanations and numerator/denominator evidence. Issue counts can overlap.
- Focused inventory replaces the card catalogue while inspecting a location. Back restores filters and keyboard focus. Refresh preserves filters. Inventory shows semantic status badges, last Intune check-in age and readable assignment state; raw location remains in device details and CSV.
- Source freshness, unassigned/review counts and observed score history. Earlier data is not synthesized; the UI displays only matching policy/mapping revisions.

## Cross-source geographic matches

The current React home page has a separate **Intune and SolarWinds location matches** table. It compares populated Intune reporting locations with active SolarWinds `City`/`ITSM_Location` evidence at city, country or region level. Search, match-status filtering and CSV export retain the source-label evidence and node counts.

This is a read-only geographic report, not an office-link approval or a Combined health score. Office names, canonical IDs, exact assignments and review decisions remain unchanged. Greater Noida and Noida stay distinct. Cloud labels are not treated as physical sites. Contradictory source cities/countries are excluded; countries and regions are not silently promoted to office-level precision. Known city spellings and countries use explicit geography knowledge, not fuzzy similarity or an LLM decision.

The Location Health score table also offers **Geographic matches** as a separate scoring scope. It applies the normal score policy to the Intune records assigned to each reporting location and SolarWinds nodes with matching city, country or region evidence. The match level is shown and exported. A geographic score does not establish an office assignment; multiple rows may share nodes, so their counts must not be summed. Freshness, field coverage and mapping-review gates still apply. The **Assigned locations** scope continues to use canonical device assignments. Geographic scoring does not modify assignments or approvals.

Unassigned endpoints are reported separately and are not a named Intune location. A missing SolarWinds snapshot is unavailable, not zero coverage. Locations without unambiguous source evidence stay unmatched. The same SolarWinds node can support multiple geographic reporting rows, such as a country and a city or two offices in that city; do not sum these rows into fleet totals. The freshness metadata identifies the saved source observations, not current physical presence.

## Reading and acting on a card

Cards distinguish device health attention from data or location-mapping attention. A card needing attention shows one main reason and an action that opens the relevant inventory, location reviews or saved evidence. Issue selection follows the chosen score mode; an endpoint score does not prioritise unrelated infrastructure issues. Reloading evidence reads the latest saved data and does not start a source synchronization.

Green cards keep component percentages, inventory and evidence inside an expandable details section. Other cards also retain their full component breakdown, individual issue filters and source evidence there. Issue counts can overlap and are never added into a unique affected-device total.

The default automatic mode remains available for browsing. A comparison note explains that it can show different score modes side by side; choose one score mode and a reporting level for consistent comparisons. Exact counts explain a weak-component Red override or a rounded score at a colour threshold.

## Score policy `location-v2`

C = confirmed compliant endpoints / eligible active assigned endpoints.

H = Up nodes / eligible active monitored assigned nodes. Explicitly Unmanaged nodes are excluded and remain visible separately. This is current node status, not measured uptime/SLA.

R = endpoints with a valid successful Intune check-in within seven days / eligible active assigned endpoints.

Each component requires at least **95% known field coverage**, an eligible nonzero denominator and a fresh source. Missing timestamps or unknown statuses do not become a healthy zero or a certified failure. Check-in timestamps more than five minutes in the future are invalid.

- **Endpoints:** `(40C + 25R) / 65`.
- **Infrastructure:** `H`.
- **Combined:** `0.40C + 0.35H + 0.25R`, only with both usable sources.

All score modes require the group's assignments to have no unresolved mapping review. Pending rules with a proposed location retain tentative assignment evidence (`review`); rejected rules do not assign a location. Policy `location-v2` and resolver `assignment-v3` keep these approval rules distinct from earlier observations. Weights and numerical bands have not changed.

Green means >=90; Warning means 75–<90, Down/Critical node attention, or a failed latest refresh while the previous successful snapshot is still fresh. Red means <75 or a required component <75. Unavailable scores are grey. These are initial operating bands, not industry-certified targets. Compare scores within the same mode and reporting level. No automatic business-critical outage override is claimed without authoritative service/criticality mapping.

Scores and colour thresholds use exact numerator/denominator ratios. Rounding is for display only: a score shown as 90.0 can remain Warning if the exact score is below 90, and a component shown as 75.0 can still trigger Red if its exact percentage is below 75.

The source freshness window is the existing backend contract: `max(900, SYNC_INTERVAL_SECONDS × 2.5)`, currently 25 minutes. An old successful snapshot can be displayed as stale but cannot supply a current score. A database failure returns unavailable rather than an empty successful inventory.

## Database setup and maintenance

For a new deployment or an existing checkout:

```powershell
python -m alembic upgrade head
python scripts/manage_locations.py              # preview; transaction is rolled back
python scripts/manage_locations.py --apply      # bootstrap/backfill; commit
```

Initial bootstrap data is `app/data/location_seed.json`. It contains source keys, locations and review notes, not workbook device counts. It is used only if the database has no mapping rules; later syncs never overwrite database rules from this file.

To replace rules, provide a complete JSON revision with a `rules` array. Each rule has `source_system` (`INTUNE` or `SOLARWINDS`), `match_key`, optional `location` and optional `review_note`:

```powershell
python scripts/manage_locations.py --rules reviewed-rules.json
python scripts/manage_locations.py --rules reviewed-rules.json --apply
```

Validation rejects duplicate/conflicting source keys before changing any rule. Replacement disables rules omitted from the complete revision and recomputes active assignments. Backfill preserves source status, source IDs and last-sync timestamps; mapping changes can update the CI's ordinary modification time. Preview first and coordinate with the sync worker during application. Changes roll back on failure.

Approval is now an explicit database field. Source notes are informational and never decide runtime approval. Bootstrap knowledge contains explicit approval states. Migration preserves the old approved/review distinction once, with reviewer/date blank for legacy decisions. New, changed-target or re-enabled imported rules are Pending; unchanged approved targets retain their reviewer/date. Bulk approval in the reference file is not independent verification of office identity. Country, city, cloud and business-unit groups remain labelled distinctly.

Use **Infrastructure → Location Health → Review location mappings** for Pending/Approved/Rejected decisions, reviewer name, server-recorded review date and before/after decision history. See [Location review workflow](LOCATION_REVIEW_WORKFLOW.md) for operation and trust boundaries.

## API

- `GET /api/v1/locations`: all reporting locations, scores, source coverage and freshness.
- `GET /api/v1/locations/matches`: read-only geographic matches, unmatched named Intune locations, source-label evidence, conflicting-node counts and freshness. No assignments or group approvals are written.
- `GET /api/v1/locations/geographic-scores`: read-only geographic-match scores with match level, components, freshness and policy version; reporting scopes may overlap.
- `GET /api/v1/locations/{id}/score`: one location's components, denominators, reasons and provenance.
- `GET /api/v1/locations/{id}/devices`: `source`, `issue`, `search`, `page`, `page_size`.
- `GET /api/v1/locations/{id}/export`: the same source/issue/search selection, CSV formula-safe output.
- `GET /api/v1/locations/{id}/history`: real observations, newest first; default last 48 samples.

`unassigned` is a supported inventory scope with no health score. Issue values include `noncompliant`, `other_compliance`, `old_checkins`, `old_30d`, `invalid_checkins`, `up`, `down`, `critical`, `warning`, `unmanaged` and `conflict`.

Cards and lists share the same issue predicates. Counts can change between requests as new snapshots arrive; the UI discloses mismatches and refreshes an out-of-range page. Each response identifies its observation time. This is not a frozen snapshot browsing service.

History is appended inside the same source savepoint as inventory, retirement and the successful source audit. Capture failure rolls all of those changes back and persists a failed source audit. There is no fabricated historical trend. Operational retention should be configured for long-running installations; this release does not delete existing observations automatically.

Score reads bracket inventory, source freshness and location metadata with source-run, inventory-update and mapping/location revision markers. A concurrent supported writer causes a retry, up to three attempts. Continuous changes return HTTP 503 rather than mixing old counts with a newer source timestamp. This optimistic coherence check assumes writes follow the application's synchronization/mapping contracts; it is not an immutable snapshot browsing service or a guarantee for arbitrary direct SQL edits. No transaction is discarded inside ingestion capture.

## Validation and limits

The test suite covers matching boundaries, rule replacement, idempotent backfill, unchanged-health sync persistence, blank/unknown/stale data, field coverage, unmanaged nodes, exact card/list counts and observed history. Browser journeys cover cards, filters, export and phone-width layout. Third-party chart rendering and font downloads are stubbed in those navigation tests; live browser verification uses the real portal assets.

SQLite migration/backfill and live APIs were verified locally. PostgreSQL-compatible SQL/model types are implemented, but a live PostgreSQL cluster was not available for deployment validation. Scores reflect source records, assigned reporting location and a provisional policy—not current physical presence, physical-asset deduplication or end-to-end business availability.
