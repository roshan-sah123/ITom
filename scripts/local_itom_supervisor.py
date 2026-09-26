"""Keep the local FastAPI scheduler and frontend server alive on Windows."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PORT = 8080
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOGS / "local_itom_service.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("itom.local_service")
stop = threading.Event()
CONTROL_ID = hashlib.sha256(str(ROOT).casefold().encode("utf-8")).hexdigest()[:16]
MUTEX_NAME = f"Local\\ITOMPortalSupervisor-{CONTROL_ID}"
EVENT_NAME = f"Local\\ITOMPortalShutdown-{CONTROL_ID}"


def _windows_kernel32():
    """Return Win32 calls with pointer-safe signatures for named controls."""
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.ResetEvent.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


def _service_control(action: str) -> int:
    """Stop, restart, or report the one supervisor for this checkout."""
    if action == "status":
        ready = service_is_ready(LOCAL_PORT)
        print(f"Portal / API / database: {'READY' if ready else 'NOT READY'} (http://127.0.0.1:{LOCAL_PORT}/)")
        if ready:
            try:
                request = Request(f"http://127.0.0.1:{LOCAL_PORT}/api/v1/system/freshness")
                with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
                    freshness = json.loads(response.read(16_384).decode("utf-8"))
                print(f"Telemetry freshness: {freshness.get('overall_status', 'UNKNOWN')}")
            except Exception as exc:
                print(f"Telemetry freshness: UNAVAILABLE ({type(exc).__name__})")
                return 1
        return 0 if ready else 1

    kernel32 = _windows_kernel32()
    if kernel32 is None:
        print(f"Supervisor {action} is supported on Windows only.")
        return 2
    event_handle = kernel32.OpenEventW(0x0002, False, EVENT_NAME)
    if event_handle:
        kernel32.SetEvent(event_handle)
        kernel32.CloseHandle(event_handle)
    elif action == "stop":
        print("Local supervisor is not running.")
        return 0
    if action == "stop":
        print("Stopping the local portal and background sync gracefully.")
        return 0

    # Wait for the supervisor to release its singleton mutex before relaunching.
    deadline = time.monotonic() + 20
    while True:
        mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        acquired = kernel32.WaitForSingleObject(mutex, 0) in (0, 0x80)
        if acquired:
            kernel32.ReleaseMutex(mutex)
            kernel32.CloseHandle(mutex)
            break
        kernel32.CloseHandle(mutex)
        if time.monotonic() >= deadline:
            print("The existing supervisor did not stop within 20 seconds.")
            return 1
        time.sleep(0.25)
    return _launch_background()


def _launch_background(open_browser: bool = False) -> int:
    """Start the local supervisor detached, then confirm the portal/API responds."""
    command = [sys.executable, str(Path(__file__).resolve())]
    if open_browser:
        command.append("--open-browser")
    try:
        subprocess.Popen(
            command, cwd=ROOT, env=service_environment(), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"Could not start the local supervisor: {exc}")
        return 1
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if service_is_ready(LOCAL_PORT):
            print("Local portal and database are ready at http://localhost:8080/.")
            return 0
        time.sleep(1)
    print("Local service did not become ready. Check logs/local_itom_service.log and logs/local_8080.log.")
    return 1


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


def service_is_ready(port: int) -> bool:
    """Check API/database readiness and portal HTML on one listener."""
    try:
        request = Request(f"http://127.0.0.1:{port}/ready", headers={"Accept": "application/json"})
        # Loopback probes should never be routed through a workstation proxy.
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            body = response.read(16_384).decode("utf-8", errors="replace")
        readiness = json.loads(body)
        if not (
            readiness.get("status") == "ready"
            and readiness.get("database") == "connected"
            and readiness.get("migration_head") is True
        ):
            return False
        portal_request = Request(f"http://127.0.0.1:{port}/", headers={"Accept": "text/html"})
        with build_opener(ProxyHandler({})).open(portal_request, timeout=3) as response:
            portal_html = response.read(32_768).decode("utf-8", errors="replace")
        return "Coforge ITOM Operations Portal" in portal_html
    except Exception:
        return False


def run_service(name: str, command: list[str], port: int) -> None:
    """Restart one child service after an unexpected exit until asked to stop."""
    port_warning_logged = False
    while not stop.is_set():
        if port_is_open(port):
            if not service_is_ready(port):
                if not port_warning_logged:
                    log.error(
                        "%s port %d is occupied by a service that is not ready; "
                        "leaving it untouched and checking again.", name, port,
                    )
                    port_warning_logged = True
                stop.wait(15)
                continue
            if port_warning_logged:
                log.info("%s is healthy again on port %d.", name, port)
                port_warning_logged = False
            # Reuse a healthy instance to avoid duplicate local servers.
            stop.wait(15)
            continue
        port_warning_logged = False
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
    parser = argparse.ArgumentParser(description="Run and manage the local ITOM portal services.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--status", action="store_true", help="Check API, database, frontend, and data freshness")
    actions.add_argument("--stop", action="store_true", help="Gracefully stop this checkout's local services")
    actions.add_argument("--restart", action="store_true", help="Restart this checkout's local services")
    actions.add_argument("--background", action="store_true", help="Start the local services in the background")
    parser.add_argument("--open-browser", action="store_true", help="Open the portal after startup")
    args = parser.parse_args()

    if args.status:
        return _service_control("status")
    if args.stop:
        return _service_control("stop")
    if args.restart:
        return _service_control("restart")
    if args.background:
        return _launch_background(open_browser=args.open_browser)

    mutex_handle = None
    shutdown_handle = None
    kernel32 = _windows_kernel32()
    if kernel32:
        mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if kernel32.WaitForSingleObject(mutex_handle, 0) not in (0, 0x80):
            log.info("Another ITOM local supervisor already manages this checkout.")
            kernel32.CloseHandle(mutex_handle)
            return 0
        shutdown_handle = kernel32.CreateEventW(None, True, False, EVENT_NAME)
        if not shutdown_handle:
            kernel32.ReleaseMutex(mutex_handle)
            kernel32.CloseHandle(mutex_handle)
            raise ctypes.WinError(ctypes.get_last_error())
        kernel32.ResetEvent(shutdown_handle)

        def watch_shutdown_event() -> None:
            while not stop.is_set():
                if kernel32.WaitForSingleObject(shutdown_handle, 500) == 0:
                    stop.set()
                    return

        threading.Thread(target=watch_shutdown_event, name="itom-shutdown-event", daemon=True).start()

    python = sys.executable
    processes = [
        threading.Thread(
            target=run_service,
            args=("ITOM Portal / API", [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(LOCAL_PORT)], LOCAL_PORT),
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
    if args.open_browser:
        # Allow startup services a moment to bind before opening the local portal.
        time.sleep(3)
        webbrowser.open(f"http://localhost:{LOCAL_PORT}/")
    log.info("Single-port local portal supervisor started on port %s.", LOCAL_PORT)
    try:
        while not stop.wait(1):
            if any(not thread.is_alive() for thread in processes):
                log.error("Service supervisor thread stopped unexpectedly")
                return 1
    finally:
        stop.set()
        for thread in processes:
            thread.join(timeout=15)
        if kernel32 and shutdown_handle:
            kernel32.CloseHandle(shutdown_handle)
        if kernel32 and mutex_handle:
            kernel32.ReleaseMutex(mutex_handle)
            kernel32.CloseHandle(mutex_handle)
        log.info("Local supervisor stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
