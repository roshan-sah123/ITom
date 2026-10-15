# Source-backed operational data

- Display operational figures from validated source ingestion and the configured SQLite/PostgreSQL database. Never substitute sample records or historical constants when an API fails.
- Show missing, stale, empty, and failed states explicitly. Identify calculated health and forecasts as derived values; they are not direct source measurements.
- Describe unsupported features as unavailable or planned. Inspect the active implementation before labeling a feature unsupported.
- Synthetic fixtures belong only in clearly isolated tests, never the operational database or dashboard.
