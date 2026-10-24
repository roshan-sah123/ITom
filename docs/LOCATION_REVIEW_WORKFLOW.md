# Location mapping review workflow

Implemented 12 October 2026 for the local portal. Open **Infrastructure → Location Health → Review location mappings**.

## Operator workflow

1. Start with Pending rules. Filter by source or search a prefix, source alias or reporting location.
2. Open the source key. Check its original source note, proposed reporting location and currently linked-device count. Counts reflect current assignment provenance; overlapping SolarWinds source fields can affect additional devices.
3. Choose an existing reporting location and a decision. Rejection requires a reason; an approval comment is optional.
4. Save review. The server records the review date/time, preserves before/after rule evidence and re-evaluates the source's active device assignments in the same transaction.
5. Read the saved reviewer/date and decision history. Back to location health reloads the scorecards after a saved change.

| Status | Assignment and score behaviour |
|---|---|
| Pending | A proposed location can remain visible as tentative `review` evidence. Groups containing pending assignment reviews have no usable health score. A rule without a proposed location leaves records unassigned. |
| Approved | Requires a reporting location. The resolver uses it as a mapped assignment. Normal source freshness and field-coverage gates still apply. |
| Rejected | The rule does not assign devices to its proposed location. Devices remain unassigned unless another independent valid SolarWinds source field resolves them. Intune never falls through a rejected longer prefix to a shorter prefix. |

Approving an alias does not override a real conflict between different source locations. Resolve that discrepancy by reviewing the appropriate target or correcting upstream source data through its owner.

## Reviewer, dates and audit

- `location_mapping_rules` stores `approval_status`, `reviewed_by` and `reviewed_at` alongside the target and revision.
- `location_mapping_reviews` stores append-only review events with reviewer, server date/time, reason and copies of the rule before and after the decision.
- The date is set by the server; client-supplied dates are not accepted. Pending decisions also record who last reviewed the rule and when.
- Existing inherited approvals are labelled **Legacy approval**. No reviewer or date was invented. Re-approve them after actual verification to record a human decision.
- Notes containing words such as “conflict” do not control future approval. Migration used the previous distinction once to preserve existing review flags; runtime and bootstrap rules now use explicit status.
- A new rule, changed target or re-enabled rule imported through `manage_locations.py` requires review. Reimporting the same enabled target retains approval and reviewer metadata. Existing human decisions remain in the audit table.

## Save and concurrency guarantees

The decision, revision, assignment changes and review event commit together. Failure rolls them back. The shared sync lock prevents a local review from racing an ingestion batch; SQLite also acquires a database write lock. PostgreSQL uses the existing transaction advisory lock. A stale rule revision or busy sync returns HTTP 409 so reviewers must reload rather than overwrite newer work. A cache-invalidation fault after commit does not claim the saved decision was rolled back.

Reviews update location metadata only. Source statuses, raw locations, check-in timestamps, source sync records and earlier score observations are preserved. They do not fetch from or modify Intune or SolarWinds.

## Local trust boundary

This portal currently has no authenticated user identity, so decisions are recorded under the fixed audit actor **Local portal operator** instead of collecting a reviewer name. Write requests require a loopback peer, a localhost/loopback hostname and, when supplied, a matching portal Origin; cross-site submissions are rejected. Remote queue readers receive `write_enabled=false`.

Do not expose these local review writes through a reverse proxy that hides the original client and rewrites its host/origin. An authenticated reviewer role and authorization checks are required before enabling remote or production approvals. This workflow records a decision; it does not prove that a device is physically present at the assigned location.

## API

- `GET /api/v1/locations/reviews/rules`: optional `status`, `source`, literal `search`, `page`, `page_size` (maximum 100). Returns rule counts, current reviewer/date, linked devices and reporting locations.
- `GET /api/v1/locations/reviews/rules/{rule_id}/history`: latest 50 recorded decisions.
- `POST /api/v1/locations/reviews/rules/{rule_id}/decision`: `status` (`PENDING`, `APPROVED`, `REJECTED`), `reviewer`, nullable `location_id`, `expected_revision` and optional `comment`.

Review decision history is immutable through this API. Rule import operations are not a full immutable catalogue-version ledger; durable rename identity and complete import auditing remain separate lifecycle improvements.

## Installation and verification

Migration `0007_location_review` adds approval fields, status/approved-target constraints, review queue indexes and the review-event table. A populated-copy upgrade/downgrade check and live pre-install backup were completed. Assignment backfill moved active records to resolver `assignment-v2` without changing source telemetry or source timestamps.

The local install retained 185 inherited approvals and 65 pending rules. No production review decisions were submitted during implementation. The original device telemetry hash and device/history/sync/score row counts matched after migration; foreign-key checks passed. These are installation observations, not permanent fleet baselines.

Automated coverage includes approval/rejection, reviewer/date/history, required-target/reason validation, stale revisions, busy syncs, rollback after assignment failure, post-commit cache failure, note-independent decisions, preserved rejection provenance, periodic ingestion, changed-target re-review, literal queue search, local/remote/Origin/hostname boundaries and the browser approval/back/mobile flow. Live PostgreSQL was not available for deployment validation.

Final verification: **332 default tests passed, two existing migration expected failures, 41 subtests passed; 42 browser journeys passed**. The final local-host guard and browser approval journey were also checked together after installation. The running queue and decision form were visually inspected without submitting a live decision.

![Live review queue](../outputs/location-reviews/review-queue.png)

![Live review form](../outputs/location-reviews/review-form.png)
