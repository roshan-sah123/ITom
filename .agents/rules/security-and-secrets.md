# Security and secrets

- Load credentials from environment variables or approved secret storage through Pydantic settings. Never print or commit secrets; `.env.example` contains placeholders only.
- Keep local databases, raw telemetry, exports, and backups outside web roots and container images. Local services bind to loopback; shared access requires an authenticated gateway and authorization for sync operations.
- Escape untrusted values inserted into HTML using the existing shared helper, or use `textContent`. Preserve CSV formula-injection protection.
- Graph inventory and SolarWinds operations remain read-only. Preserve GET/SELECT guards for telemetry; OAuth token acquisition is a required authentication POST, not an inventory mutation.
- Return safe error summaries and run IDs. Do not serialize raw exception messages, stack traces, or private diagnostic context to portal clients.
