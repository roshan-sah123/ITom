# ITOM security status — 15 October 2026

## Completed cleanup

- Removed the Compose mount that exposed raw `data/` files, including the local SQLite database. NGINX explicitly rejects `/data` and `/data/` paths.
- Bound the Compose portal to loopback by default. Removed the known fallback database password; Compose requires `POSTGRES_PASSWORD`.
- Sync API responses now replace stored error messages with a safe summary and hide stack traces and diagnostic context, including old records. Error codes and run IDs remain available for investigation.
- Removed obsolete proxy directives and duplicated agent guidance. Generated output and temporary test directories are excluded from Git and image builds.

## Remaining work before shared access

1. Enforce authentication and authorization at a verified gateway or in the application. Inventory APIs currently have no sign-in.
2. Restrict manual sync to authorized operators and add a cooldown/rate limit. It remains unauthenticated within the deployment boundary.
3. Audit current direct and transitive dependency advisories. This review did not perform that audit.

Keep local deployments on loopback. See [deployment instructions](DEPLOYMENT.md) before changing network exposure. Existing deployments need their configuration updated and restarted; editing these files does not change running services. Rotate the database password if the old fallback was used.

## Verification

154 focused API, ingestion, scheduler, source-safety, and deployment tests passed. The new diagnostic-disclosure test failed before the fix and passed afterward for list, latest, and detail endpoints. Source TLS checks, SWQL mutation guards, hostile search handling, and read-only inventory protections remain covered.

Docker and NGINX executables are unavailable in this environment, so container startup and live proxy behavior were not exercised. No live source sync, production database change, or deployment was performed.
