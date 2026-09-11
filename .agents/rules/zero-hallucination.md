# Zero-Hallucination Policy

## Core Invariant
- **Never create, display, or commit mock/simulated numbers for executive metrics.**
- All figures displayed on OPS Analytics, CMDB, Intune, or SolarWinds views must originate strictly from verified API extractions (Microsoft Graph Intune API or SolarWinds SWIS API) or the persistent PostgreSQL database.
- Any non-integrated sections (Network CMDB, DEX, etc.) must strictly display clean **"Coming Soon / Phase 2"** pipeline cards. Never fabricate numbers or simulate chart activity to fill empty sections.
- For testing and verification, never use synthetic mock figures to assert production metrics unless explicitly labeled as unit test stubs.
