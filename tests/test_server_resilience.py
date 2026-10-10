"""Deployment entry points must launch the current FastAPI application."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_systemd_runs_current_backend():
    content = (ROOT / "systemd" / "itom.service").read_text(encoding="utf-8")
    assert "-m uvicorn app.main:app" in content
    assert "--host 127.0.0.1" in content
    assert "Restart=always" in content
    assert "network-online.target" in content


def test_windows_launcher_runs_current_supervisor():
    content = (ROOT / "start_itom_service.bat").read_text(encoding="utf-8")
    assert "scripts\\local_itom_supervisor.py" in content


def test_current_task_registration_runs_supervisor():
    content = (ROOT / "scripts" / "register_local_itom_task.ps1").read_text(encoding="utf-8")
    assert "local_itom_supervisor.py" in content
    assert "RestartCount" in content
    assert "ExecutionTimeLimit" in content
