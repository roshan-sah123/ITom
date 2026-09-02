---
name: Feature Request
about: Suggest an idea, enhancement, or new capability for the ITOM platform
title: '[FEAT] <concise description of feature proposal>'
labels: ['enhancement', 'needs-review']
assignees: ''
---

## 🚀 Feature Description & Problem Statement
Is your feature request related to a problem or operational inefficiency? Please describe concisely.
*Example: As an Operations Lead, I need to filter SolarWinds nodes by CPU utilization threshold so that I can quickly identify throttled hosts.*

## 💡 Proposed Solution
Describe the solution you would like to see implemented.
- Which tier will this impact? (Presentation / Ingestion / Persistence / API)
- Are new UI components, charts, or tables required?
- Are new API endpoints or SWQL/Graph queries necessary?

## 🔄 Alternative Solutions Considered
Describe any alternative approaches or workarounds you have evaluated and why they were insufficient.

## ⚖️ Zero-Hallucination & Mathematical Invariant Considerations
- Does this feature impact any authoritative invariants (25,987 Intune devices, 1,548 SolarWinds nodes, 1,548 CMDB CIs, 28,955 fleet assets)?
- How will the metrics be verified against raw upstream API extractions?

## 📋 Implementation & Acceptance Checklist
- [ ] Backend ingestion client / normalization engine updated
- [ ] Zero-build frontend components integrated with `escapeHtml()` sanitization
- [ ] Invariant test suite added/updated under `tests/`
- [ ] E2E test runner (`python tests/run_e2e_tests.py`) passes 100%
- [ ] Documentation updated in `docs/` and `README.md`
