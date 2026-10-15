# Telemetry reconciliation

- Reconcile each source against its latest successful complete extraction, sync-run counts, and active database rows. Historical fleet sizes and percentages are not acceptance criteria.
- Use configured sync cadence and persisted successful timestamps for freshness. A failed attempt does not make older inventory fresh.
- Keep Intune compliance/check-in evidence distinct from SolarWinds node status and resource measurements. Inspect `app/services/telemetry_sources.py` for the actual health mapping and thresholds instead of copying rules into documentation.
- Scope totals, filters, exports, and drilldowns to the selected source and population. Distinguish source records from unique physical devices.
