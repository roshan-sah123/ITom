# Workspace guide

## Run the portal

From the repository folder in PowerShell:

```powershell
.venv\Scripts\python.exe scripts/local_itom_supervisor.py --background
.venv\Scripts\python.exe scripts/local_itom_supervisor.py --status
```

Open [the local portal](http://localhost:8080/). Use the supervisor's `--restart`
option after changing backend code. The running app owns scheduled source sync.

## Test changes

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest tests/browser --run-browser -q
```

Tests use isolated databases. Browser tests use synthetic inventory and temporary
local servers; they do not require a live Intune sync.

## Where work is saved

| Folder | Contents |
| --- | --- |
| `frontend/`, `app/`, `src/` | Application source saved in Git. |
| `tests/`, `docs/` | Automated checks and documentation saved in Git. |
| `data/` | Live local database; keep private and retain. |
| `backups/` | Private recovery copies, including saved location rules. |
| `outputs/intune-location-rd-2026-10-22/` | Private location research and audit artifacts. |
| `output/playwright/` | Browser screenshots and verification evidence. |
| `.task-temp/`, `scratch/` | Local experiments and temporary test artifacts. |

Source commits do not contain the database, research exports or credentials.
Keep `.env`, databases and backups out of static hosting and version control.

## Keep it clean

Remove generated Python/pytest caches and finished isolated test databases when
no tests are running. Retain live databases, recovery copies, research workbooks,
operator scripts, and evidence that cannot be regenerated. Historical guides
remain under `docs/archive/`; start with [the documentation index](README.md).
