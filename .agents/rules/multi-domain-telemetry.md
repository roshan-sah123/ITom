# Multi-Domain Telemetry Standards

## Dynamic Synchronization & Invariant Reconciliation
All metrics displayed across the ITOM Portal are dynamic and derive from periodic synchronization cycles (`APScheduler` 10-minute worker, `sync_runs` table, or on-demand sync). Data freshness headers (`last_synchronized_at`, `data_age_seconds`, `sync_status`) must accompany API responses and header status indicators.

### Baseline Reference Invariants
Initial forensic extractions establish the baseline invariants below; live queries will naturally reflect new enrollments, retirements, or status changes:

- **Microsoft Intune (Baseline Reference: ~25,987 Endpoints)**:
  - Multi-platform fleet spanning Windows, macOS, Linux, iOS, and Android.
  - Compliance states: Compliant, Non-Compliant, ConfigManager, Unknown, InGracePeriod.
  - Fleet disk utilization: Baseline ~37.4% average across reporting endpoints.
  - Invariant: Compliance totals and storage utilization must mathematically reconcile with raw Graph datasets or database CI records without arbitrary drift.

- **SolarWinds Orion (Baseline Reference: ~1,548 Server Nodes)**:
  - Monitored server infrastructure (~1,543 active CIs).
  - Health Tier Classification Rules:
    - **High**: Status is `Up` (1) AND CPU Load < 75% AND Memory Used < 80%.
    - **Medium**: Status is `Warning` (3) OR (CPU Load between 75% and 90%) OR (Memory Used between 80% and 90%).
    - **Low/Critical**: Status is `Down` (2) / `Critical` (14) OR CPU Load > 90% OR Memory Used > 90%.

### Dynamic Header Switching
- Active navigation tabs must dynamically adapt telemetry metrics in the header to match the selected domain (e.g., active endpoint count when on Intune, server node count when on SolarWinds, total CIs when on CMDB).
