# Senior engineering review: canonical locations and scorecards

**Update, 10 October 2026:** Both reproduced P1 defects below have been addressed with rollback and reader/writer regressions. The original review is retained as historical evidence. See [the product refinement and verification report](LOCATION_PRODUCT_REVIEW_2026-10-10.md) for the current 78/100 engineering-readiness assessment and remaining P2 limits.

Reviewed 9 October 2026 using the code-review-and-quality skill and the repository backend guidance. Scope: models, migration, rules/resolver, backfill CLI, ingestion integration, score/list/export/history APIs, frontend interactions and tests. No runtime implementation, workbook or production data was changed by this review. Live checks were read-only; defect probes used isolated databases with no upstream requests.

## Verdict and confidence

**Request changes before production rollout. Engineering readiness confidence: 65/100.**

The implementation fits the current application and its ordinary workflows work. However, two reproduced integrity defects can invalidate the relationship between inventory, source audit status and score freshness. These findings matter more than a green happy-path suite. The earlier 85/100 implementation assessment was too optimistic as a production-readiness signal.

This is a judgment-based engineering assessment, not a probability of correctness or a measured accuracy percentage for physical location assignments.

| Dimension | Score | Main reason |
|---|---:|---|
| Correctness and data integrity | 19/35 | Failed-history transaction and mixed-epoch response defects reproduced. |
| Architecture and maintainability | 14/20 | Good shared resolver and database ownership; free-text control, mutable revisions and name-derived identity weaken lifecycle management. |
| Verification | 16/20 | Current automated checks pass, but they did not catch the reproduced failure/concurrency paths. Live PostgreSQL remains unverified. |
| Performance and lifecycle | 8/15 | Python pagination loads the whole location; full catalog rescans records; history lacks retention. |
| Feature security boundaries | 8/10 | Parameterized queries, escaped HTML, read-only source integrations and CSV formula protection are present. Application authentication concerns from the earlier audit remain outside this feature's fixes. |
| **Total** | **65/100** | **Two P1 blockers require correction.** |

## Findings in priority order

### P1 — Failed score-history capture can commit inventory changes

References: `app/services/sync_service.py:402`, `:423`, `:452`, `:536`.

Inventory ingestion and retirement are protected by a nested transaction, but that scope ends before `LocationService.capture()` executes. If capture raises a non-aborting exception, `sync_single_source()` records FAILED and returns normally. `execute_sync_with_lock()` subsequently commits the session. The error log claims inventory was rolled back, but it was not.

**Reproduction:** In an isolated database, start with a Compliant CI, ingest a NonCompliant observation, and make only history capture raise RuntimeError. Overall status and persisted SyncRun status are FAILED, yet the persisted CI is NonCompliant and its location assignment is committed.

**Impact:** Current inventory can advance without an authoritative successful source run. Source freshness and audit records can describe an older snapshot while readers see newer data. Success-only summary invalidation also does not run for the failed result.

**Required remedy:** Make the transaction boundary explicit. Either capture participates in the same atomic scope and a capture failure rolls back inventory/retirement, or derived history is isolated as a non-fatal post-commit operation with its own error reporting. A source run must never claim failed-and-rolled-back while refreshed inventory commits. Add a regression reproducing capture failure, including an existing CI update and retirement.

### P1 — A score can combine old inventory with newer source freshness

References: `app/services/location_service.py:213`, `:217`, `:219`, `:270`, `:274`.

The service reads/materializes CI observations and then separately reads successful-sync/freshness records. It does not enforce a coherent database read snapshot or verify that the source revision stayed unchanged across those statements. SQLite legacy read transaction behaviour and PostgreSQL READ COMMITTED do not guarantee the intended cross-statement snapshot.

**Reproduction:** Use two sessions against an isolated SQLite file. After the reader materializes the old Compliant observation, the writer commits NonCompliant plus a newer successful run. The reader then obtains new freshness. Its response is 100% compliance, Endpoint score 100/healthy and FRESH, while the current database CI is NonCompliant. The source timestamp belongs to the newer run, not to the counts used for that score.

**Impact:** This breaks the advertised source/freshness contract and can create a false-green response during ordinary concurrent sync activity. The frontend's count-mismatch notice between separate requests cannot repair a response that is internally inconsistent.

**Required remedy:** Use an explicitly enforced consistent read transaction appropriate to each database, or pin/read source observation versions and retry if they change while building the response. Bind counts, membership, mapping revision and freshness to the same observed state. Add a reader/writer concurrency regression for both catalogue and individual scores. Validate this on PostgreSQL as well as SQLite.

### P2 — Review state is inferred from free-text notes

Reference: `app/services/location_service.py:107`.

Presence of the words `conflict` or `versus` in a note sets resolution to review. This is not a reliable machine-readable decision.

**Reproduction:** The note `No conflict; all assignments verified.` still produces `review`. Conversely, another description of unresolved ambiguity can avoid both keywords and be treated as mapped. A note about one device can also apply the review flag to every device matched by the same alias.

**Remedy:** Store explicit rule resolution/review-required status and structured per-device conflict evidence. Keep explanatory notes separate from logic. Tests should cover resolved notes, ambiguous notes and a single conflicting device within an otherwise valid group.

### P2 — Location rename/revision lifecycle does not preserve identity or a reconstructable audit

References: `app/services/location_service.py:139`, `:151`, `:163`; `app/models/location.py:16`.

The provided rule-update format derives a location ID from its display name. Changing the target's display name creates a different location ID and leaves the former location in the catalogue. It cannot express a same-identity rename. Existing mapping-rule rows are updated in place, so old revision hashes do not preserve the corresponding rule content.

**Reproduction:** Replace one prefix rule targeting Original office with the same key targeting Renamed office. Backfill changes the CI's location ID and the old location remains. This may be a move or a rename, but the supplied workflow cannot distinguish them.

**Remedy:** Use durable site codes/IDs independent of display names, accept explicit target IDs in updates, and maintain immutable mapping revision content/audit records. Define moves, renames and retirement separately. Preserve history for a true rename and do not group unrelated same-named cities merely by display text.

### P2 — Pagination and storage lifecycle are not production-scale controls

References: `app/services/location_service.py:199`, `:213`, `:277`, `:290`; `app/api/v1/endpoints/locations.py:58`.

Every inventory page materializes every matching CI, including full attributes, then applies issue/search filtering and slicing in Python. The catalogue scans all active score records per request. Export builds the complete CSV in memory and silently caps items at one million even though its record-count header reflects the full selection. Score snapshots have no retention or compaction policy.

**Observed local measurements:** One catalogue request took 8.11 seconds. A 25-row page for a location containing 5,206 records took 3.47 seconds. These are single measurements during local review/test activity, not controlled p95 load benchmarks.

**Storage estimate:** The observed snapshot JSON averaged 1,227 bytes. At 84 populated groups, two source snapshots per ten-minute cycle and that payload size, raw JSON alone projects to about 10.09 GiB/year. Row/index/WAL/backup overhead is additional. This is an estimate assuming stable cadence and group count, not an observed annual footprint.

**Remedy:** Push shared issue/search/count/pagination predicates into the database, materialize typed check-in fields where needed, and use snapshot/mapping-version-aware aggregates. Stream or chunk exports and disclose any explicit export limit. Set a justified retention/aggregation policy for observed history and test representative concurrency and load. Do not delete historical data without an agreed retention policy.

## Positive findings

- Runtime location ownership is in the database; Excel is not read by APIs or syncs.
- A common resolver is used for ingestion and backfill, including unchanged-health updates.
- Duplicate rules are rejected before replacing the catalogue; raw source values are preserved.
- The component mathematics, unmanaged exclusion, stale/unknown-data handling and 95% known-field coverage gate have direct tests.
- Card issue counts and drilldowns use the same predicates. Query failures on the new location path are not reported as successful empty inventory.
- The UI distinguishes score modes and reporting levels, discloses score overrides and handles source refresh failures.
- CSV output has protection for leading formula-trigger characters; frontend source text is escaped.
- Actual observations are stored rather than synthesizing historical trends. The UI avoids comparing mismatched mapping/policy versions.

## Verification performed

- Current default regression suite: **285 passed, 4 xfailed, 13 warnings, 41 subtests passed**.
- Focused location/migration checks: **13 passed, 2 xfailed**. The expected failures are the pre-existing migration-index/downgrade audit defects.
- Four isolated review reproductions: failed capture with committed CI changes; old counts with new freshness; resolved note producing review; same-key rename changing location ID.
- Read-only live API and SQLite measurements: catalogue latency, per-location page latency, snapshot payload footprint and current conflict count.
- Static review of migration, schema, source boundaries, query safety, UI escaping and lifecycle behaviour. Whitespace checks passed with the repository's CR-at-EOL convention.
- The three browser journeys passed during implementation; they were not rerun during this review. Those navigation tests stub third-party font/chart assets, while the implementation also received real live-browser verification.

The four existing expected failures concern embedded-NUL legacy inventory search, absent legacy migration indexes, the corresponding legacy downgrade, and swallowed datastore errors in the legacy inventory repository. They are not newly discovered feature regressions and do not explain away the new P1 findings.

## Fix order and acceptance

1. Correct the source/history transaction boundary and add its negative-path regression.
2. Guarantee cross-statement source/mapping observation coherence and add concurrent reader/writer tests.
3. Replace note-based control with explicit review state; make identity and rule revision history durable.
4. Move paging/filtering/aggregation into scalable query paths, then set history/export lifecycle policy.
5. Re-run the full suite and browser journeys, verify actual PostgreSQL behaviour, and profile representative concurrent traffic before production approval.

No evidence was collected that the current live dataset has already suffered the reproduced failure paths. The defects were demonstrated safely on isolated test data. The implementation remains suitable for controlled POC evaluation, but it should not be treated as production-approved until the P1 fixes are verified.
