"""Keep the local FastAPI scheduler and frontend server alive on Windows."""
from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOGS / "local_itom_service.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("itom.local_service")
stop = threading.Event()


def service_environment() -> dict[str, str]:
    """Strip only the refused loopback proxy injected into this shell.

    Windows user and machine proxy settings are direct and VPN paths were
    checked. Any legitimate corporate proxy setting is preserved.
    """
    env = os.environ.copy()
    for key, value in list(env.items()):
        if not key.lower().endswith("_proxy"):
            continue
        try:
            proxy = urlparse(value)
            if proxy.hostname in {"127.0.0.1", "localhost", "::1"} and proxy.port == 9:
                env.pop(key, None)
                log.warning("Ignoring invalid loopback proxy for local sync service (%s)", key)
        except ValueError:
            continue
    return env


def port_is_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.35)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def run_service(name: str, command: list[str], port: int) -> None:
    """Restart one child service after an unexpected exit until asked to stop."""
    while not stop.is_set():
        if port_is_open(port):
            # Reuse a working local instance rather than creating an endless
            # restart loop when the user already started the portal manually.
            stop.wait(15)
            continue
        try:
            log.info("Starting %s: %s", name, command)
            with (LOGS / f"local_{port}.log").open("ab") as output:
                child = subprocess.Popen(
                    command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                    env=service_environment(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            while child.poll() is None and not stop.wait(2):
                pass
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
            if not stop.is_set():
                log.error("%s exited with code %s; restarting in 5 seconds", name, child.returncode)
                stop.wait(5)
        except Exception:
            log.exception("Could not start %s; retrying in 10 seconds", name)
            stop.wait(10)


def main() -> int:
    python = sys.executable
    processes = [
        threading.Thread(
            target=run_service,
            args=("FastAPI / SQLite scheduler", [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], 8000),
            daemon=True,
        ),
        threading.Thread(
            target=run_service,
            args=("Frontend", [python, "-m", "http.server", "8080", "--bind", "127.0.0.1", "--directory", str(ROOT / "frontend")], 8080),
            daemon=True,
        ),
    ]
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop.set())
        except (ValueError, OSError):
            pass
    for thread in processes:
        thread.start()
    if "--open-browser" in sys.argv:
        # Allow startup services a moment to bind before opening the local portal.
        time.sleep(3)
        webbrowser.open("http://localhost:8080/")
    log.info("Local supervisor started; sync cadence is configured by the API settings.")
    try:
        while not stop.wait(1):
            if any(not thread.is_alive() for thread in processes):
                log.error("Service supervisor thread stopped unexpectedly")
                return 1
    finally:
        stop.set()
        for thread in processes:
            thread.join(timeout=15)
        log.info("Local supervisor stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
