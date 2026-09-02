# Research Analyst on Windows (NSSM — native service, no Docker)

Installs the RA API as a native Windows service using **NSSM** (Non-Sucking
Service Manager). The **PWA webapp** (ra.devinfo.dev, installable) and the
**TUI/terminal** (`research-analyst tui`) remain the primary surfaces; the
native service is for users who want a local always-on instance (sync jobs,
local API).

## Prerequisites
1. Python 3.11+ (from python.org) — check `python --version`.
2. NSSM — download from https://nssm.cc/download, put `nssm.exe` on PATH.

## Install
```powershell
# from an admin PowerShell
git clone https://github.com/nrupala/research-analyst.git C:\research-analyst
cd C:\research-analyst
python -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install .

# register the service (paths quoted)
nssm install ResearchAnalyst "C:\research-analyst\.venv\Scripts\python.exe" "-m uvicorn research_analyst.server:app --host 127.0.0.1 --port 8700"
nssm set ResearchAnalyst AppDirectory "C:\research-analyst"
nssm set ResearchAnalyst AppEnvironmentExtra PYTHONPATH=C:\research-analyst
nssm set ResearchAnalyst Start SERVICE_AUTO_START
nssm start ResearchAnalyst
```

## Verify
```powershell
curl.exe -s http://127.0.0.1:8700/api/health
nssm status ResearchAnalyst   # SERVICE_RUNNING
```

## Update
```powershell
cd C:\research-analyst
git pull --ff-only
.venv\Scripts\pip install .
nssm restart ResearchAnalyst
```

## Remove
```powershell
nssm stop ResearchAnalyst
nssm remove ResearchAnalyst confirm
```