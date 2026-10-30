# Geographic score reporting

Revision `0010_geographic_reporting` adds score observations and the exact inventory
used for each observation. After `alembic upgrade head`, the next successful source
sync creates the first observations. No historical geographic observations are
backfilled. A successful sync and its observations commit together. A failed sync
does not publish new observations. Both sources are needed for usable combined
scores. Use the API for a live recalculation between syncs; these tables are
observations at sync time, not continuously recalculated values.

The latest reporting cycle is the most recent successful `sync_runs` row after
the migration. If it contains no geographic matches, the query returns no rows;
do not fall back to older rows. Older snapshots remain available for audit.
Geographic evidence can overlap and does not establish an office assignment.
Each inventory row is a copy of the contributing CI's identity and status at
observation time; `ci_id` links to current inventory, which may since change.
This copy does not include all device attributes.

For PostgreSQL, the following query returns the latest score rows and a snapshot
identifier to use in the inventory query. Score/status reflect the observation
time, not current freshness. Verify both source timestamps and subsequent sync
failures before creating tickets; stale observations must not be treated as live.

```sql
WITH latest AS (
    SELECT id FROM sync_runs WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC, id DESC LIMIT 1
)
SELECT s.id AS snapshot_id, s.location_id, s.location_name, s.match_level,
       s.recorded_at, s.policy_version,
       s.data->'scores'->'combined'->>'value' AS combined_score,
       s.data->'scores'->'combined'->>'status' AS score_status,
       s.data->'scores'->'combined'->>'reason' AS reason,
       CASE s.data->'scores'->'combined'->>'status'
           WHEN 'critical' THEN 'P1' WHEN 'warning' THEN 'P2' ELSE NULL END AS suggested_priority,
       s.data->>'endpoints' AS intune_devices, s.data->>'nodes' AS solarwinds_nodes,
       s.data->'components' AS components, s.data->'freshness' AS source_freshness
FROM geographic_score_snapshots s JOIN latest ON latest.id = s.sync_run_id
ORDER BY s.location_name;
```

```sql
-- Replace the UUID with a snapshot_id from the previous query.
SELECT source_system, source_id, name, ci_type, status, source_location,
       checkin_at_source, last_sync_time, ci_id
FROM geographic_score_inventory
WHERE snapshot_id = '00000000-0000-0000-0000-000000000000'::uuid
ORDER BY source_system, name;
```

For one combined result with a row per contributing device:

```sql
WITH latest AS (
    SELECT id FROM sync_runs WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC, id DESC LIMIT 1
)
SELECT s.id AS snapshot_id, s.location_name, s.match_level, s.recorded_at,
       s.policy_version, s.data->'scores'->'combined'->>'value' AS combined_score,
       s.data->'scores'->'combined'->>'status' AS score_status,
       s.data->'scores'->'combined'->>'reason' AS reason,
       CASE s.data->'scores'->'combined'->>'status'
           WHEN 'critical' THEN 'P1' WHEN 'warning' THEN 'P2' ELSE NULL END AS suggested_priority,
       s.data->'freshness' AS source_freshness,
       i.source_system, i.source_id, i.name AS device_name, i.ci_type,
       i.status AS device_status, i.source_location, i.checkin_at_source, i.last_sync_time
FROM geographic_score_snapshots s
JOIN latest ON latest.id = s.sync_run_id
JOIN geographic_score_inventory i ON i.snapshot_id = s.id
ORDER BY s.location_name, i.source_system, i.name;
```

The score is repeated for each device. Do not sum repeated score or location
counts. A snapshot status is historical: use the source freshness timestamps
and latest sync attempts to decide whether it is still actionable.

Check the latest attempt for each source before using a score for tickets:

```sql
SELECT DISTINCT ON (source_system) source_system, status, started_at,
       completed_at, records_processed
FROM sync_runs
WHERE source_system IN ('INTUNE', 'SOLARWINDS')
ORDER BY source_system, started_at DESC, id DESC;
```

Compare the source timestamps in `source_freshness` with the current time and
the portal's configured freshness window. A later failed or partial attempt can
also make the current dashboard status differ from the stored observation.

Grant a dedicated reporting role read-only access to these tables and `sync_runs`,
subject to your organization's access controls. Inventory is sensitive. Plan and
test backups and a retention policy before sustained use: every successful source
sync saves a new copy of matching inventory, and geographic scopes can overlap.
The application does not automatically prune this history.
