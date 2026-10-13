# SolarWinds run failure: 11 October 2026

**Recovery, 12 October 2026:** After the user updated the configured SolarWinds credentials and the portal restarted, a live read-only fetch succeeded at approximately 16:38 IST with 1,625 nodes. The normal portal worker then completed a successful persisted SolarWinds sync at **16:39:06 IST**, processing 1,625 records; the freshness API reported **FRESH**. The previous 403 is resolved. This establishes that the updated credentials are accepted; it does not establish a specific earlier server-side expiry/lockout reason. No credential values were displayed or saved in this report.

Read-only investigation. All times below are IST.

## Confirmed cause and timeline

The SolarWinds SWIS read endpoint rejects the application's request with HTTP 403 Forbidden. The failure occurs during extraction, before normalization, database ingestion or location-score history capture.

- Last successful refresh: **08:02:03**, 1,625 records.
- First failed scheduled extraction in the current log: **08:12:04**, HTTP 403.
- Subsequent scheduled runs repeatedly fail with the same response.
- Latest run inspected: **17:14:38–17:14:40**, run `3a5b6660-60f8-4170-9d3c-3f7721eb7bd6`, FAILED, zero extracted/processed records.
- Intune in that cycle succeeded at **17:14:35**, 30,047 records. Overall sync is PARTIAL/DEGRADED.
- Freshness API at **17:21:52** reports SolarWinds STALE, still bound to the 08:02 successful observation; Intune FRESH.

## Independent verification

One GET-only query, `SELECT TOP 1 NodeID FROM Orion.Nodes`, was executed through the configured production client. It also returned 403, with server header `Microsoft-HTTPAPI/2.0`, no redirect and no explanatory body indicators. Credentials are nonempty; their validity was not established. No raw response, username, password or authorization header was printed or saved.

This confirms the HTTP access rejection and rules out location scoring or bulk ingestion as the trigger for this failed extraction. It does **not** identify the exact server-side authorization policy responsible. The client labels both 401 and 403 as “Authentication failed,” so that wording alone is not proof of an incorrect password.

## Impact and next diagnosis

SolarWinds dashboard values describe the previous successful snapshot, not current infrastructure conditions. Failed extraction is not evidence that the monitored nodes are down. Failed runs do not replace the stored fleet with an empty inventory.

The SolarWinds/SWIS administrator should inspect server authentication and authorization logs around 08:12 IST, checking account lockout/expiry, read permissions for Orion.Nodes/SWIS and any client-address or service access restrictions. A successful read-only query with the same account and client path is the recovery criterion; the next normal source run should then advance freshness.

Investigation changed no application code, credentials, source permissions, transport configuration or database inventory. The local supervisor restart at 08:23 happened after the first observed 403; the failure persisted afterwards.

Evidence: `logs/local_8080.log:92320` (first failure), `:103525` (latest inspected failure), local sync/freshness API responses, and the sanitized probe `scratch/solarwinds_access_probe.py`.
