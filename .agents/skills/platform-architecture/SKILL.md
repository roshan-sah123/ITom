---
name: platform-architecture
description: Use when designing or changing ITOM modular-monolith boundaries, integration contracts, or cross-module architecture.
---

# Platform Architecture

- Follow `docs/ARCHITECTURE.md` and `docs/PLATFORM_EXECUTION_LEDGER.md`; keep React, FastAPI routes, services, repositories, and persistence responsibilities separate.
- Preserve existing API contracts, approved UI, source evidence, and unavailable states. Prefer existing abstractions to new infrastructure.
- Source adapters own extraction and normalization; sync orchestration owns snapshot validation, locking, atomic persistence, retirement, and per-source audits.
- Use isolated tests and the 8081 environment before proposing release. Never treat a green process health probe as evidence of fresh source data.