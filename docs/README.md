# Documentation

Use this index to distinguish maintained guidance from dated evidence. New team
members should not need archived reports for normal development or operations.

## Start by role

| Role | Read first | Then use |
| --- | --- | --- |
| New developer | [Onboarding](ONBOARDING.md) | [Architecture](ARCHITECTURE.md), [data flow](DATA_FLOW.md), [API contracts](API_CONTRACTS.md), [tests](../tests/README.md) |
| Operator / DevOps | [Workspace guide](WORKSPACE_GUIDE.md) | [Deployment](DEPLOYMENT.md), [sync strategy](SYNC_STRATEGY.md), [troubleshooting](TROUBLESHOOTING.md) |
| Frontend developer | [Onboarding](ONBOARDING.md) | [Decision metrics](DECISION_METRICS.md), [inventory locations](INVENTORY_LOCATIONS.md), [Site Scores](LOCATION_SCORECARDS.md) |
| Product / service owner | [Product requirements](PRD.md) | [Project context](PROJECT_CONTEXT.md), [decision metrics](DECISION_METRICS.md), [location product review](LOCATION_PRODUCT_REVIEW_2026-10-10.md) |

## Maintained reference

### Platform

- [Architecture](ARCHITECTURE.md)
- [Data flow](DATA_FLOW.md)
- [API contracts](API_CONTRACTS.md)
- [Deployment](DEPLOYMENT.md)
- [Onboarding](ONBOARDING.md)
- [Workspace guide](WORKSPACE_GUIDE.md)
- [Testing](../tests/README.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security status](SECURITY_STATUS_2026-10-15.md)

### Data and operations

- [Sync strategy](SYNC_STRATEGY.md)
- [Decision metrics](DECISION_METRICS.md)
- [Inventory locations](INVENTORY_LOCATIONS.md)
- [Location review workflow](LOCATION_REVIEW_WORKFLOW.md)
- [Location Scorecards](LOCATION_SCORECARDS.md)
- [SolarWinds location rows](SOLARWINDS_LOCATION_ROWS.md)
- [Dashboard Site Scores](DASHBOARD_SITE_SCORES.md)

### Product and research

- [Product requirements](PRD.md)
- [Project context](PROJECT_CONTEXT.md)
- [Intune location inference](INTUNE_LOCATION_INFERENCE.md)
- [SolarWinds category dashboard research](SOLARWINDS_CATEGORY_DASHBOARD_RD_2026-10-23.md)
- [SolarWinds deep research](SOLARWINDS_DEEP_RD_2026-10-17.md)
- [VP dashboard feedback](VP_DASHBOARD_FEEDBACK.md)

## Historical evidence

Dated audits and reviews describe the system as it existed on that date; test
counts and findings in them are not current guarantees. Completed cleanup
records are in [cleanup reports](cleanup-reports/). Superseded plans, draft
requirements, and prototype evidence are indexed in [the archive](archive/README.md).

- [Codebase audit, 8 October 2026](CODEBASE_AUDIT_2026-10-08.md)
- [Dashboard data-confidence review, 8 October 2026](DASHBOARD_DATA_CONFIDENCE_2026-10-08.md)
- [Location implementation review, 9 October 2026](LOCATION_IMPLEMENTATION_SENIOR_REVIEW_2026-10-09.md)
- [SolarWinds failure review, 11 October 2026](SOLARWINDS_FAILURE_REVIEW_2026-10-11.md)
- [Frontend consistency audit](FRONTEND_CONSISTENCY_AUDIT_2026-10-14.md) and [fix record](FRONTEND_CONSISTENCY_FIXES_2026-10-14.md)

## Naming convention

Maintained documentation uses `UPPER_SNAKE_CASE.md`. Dated evidence appends
`YYYY-MM-DD`. Directory indexes remain `README.md`.
