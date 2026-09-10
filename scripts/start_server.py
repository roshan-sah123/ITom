#!/usr/bin/env python3
"""ITOM On-Premise Production Server & Auto-Sync Supervisor.

Runs:
1. Multi-threaded HTTP Server on 0.0.0.0:8080 (serves portal to local & corporate network).
2. Recurring 10-Minute Telemetry Auto-Sync Daemon in background thread.
3. Auto-restarts services if any failure occurs.
4. Dynamically resolves host IP addresses across all active network interfaces (Wi-Fi, Ethernet, VPN).
"""

import json
import os
import sys
import time
import socket
import logging
import signal
import threading
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "itom_server.log") if os.path.exists(os.path.join(PROJECT_ROOT, "logs")) else os.path.join(PROJECT_ROOT, "itom_server.log")
CRON_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "itom_cron.log") if os.path.exists(os.path.join(PROJECT_ROOT, "logs")) else os.path.join(PROJECT_ROOT, "itom_cron.log")
SYNC_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "run_sync.py")

PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")
INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", str(10 * 60)))  # 10 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("itom_server")


def get_dynamic_ips() -> list[str]:
    """Discover all reachable IPv4 addresses assigned to active network interfaces.
    
    Resolves local IPs across DHCP Wi-Fi, Ethernet, and corporate VPN adapters.
    """
    ip_list = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ip_list.add(ip)
    except Exception:
        pass

    # Connection probe method for default routing interface
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Probe Google DNS (no packet sent for UDP connect)
        s.connect(("8.8.8.8", 80))
        default_ip = s.getsockname()[0]
        s.close()
        if not default_ip.startswith("127.") and not default_ip.startswith("169.254."):
            ip_list.add(default_ip)
    except Exception:
        pass

    # Ensure 127.0.0.1 is always present as fallback
    if not ip_list:
        ip_list.add("127.0.0.1")

    return sorted(list(ip_list))


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server with socket address reuse and daemonized workers."""
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        """Bind socket with SO_REUSEADDR and (where supported) SO_REUSEPORT."""
        if hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
        super().server_bind()


class CustomHTTPHandler(SimpleHTTPRequestHandler):
    """Resilient HTTP Request Handler with REST API routes, CORS, and strict read-only guards."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def translate_path(self, path):
        clean_path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
        if clean_path.startswith("/data/"):
            rel = os.path.relpath(clean_path, "/data")
            return os.path.normpath(os.path.join(PROJECT_ROOT, "data", rel))
        if clean_path.startswith("/exports/"):
            rel = os.path.relpath(clean_path, "/exports")
            return os.path.normpath(os.path.join(PROJECT_ROOT, "exports", rel))
        rel = clean_path.lstrip("/")
        return os.path.normpath(os.path.join(PROJECT_ROOT, rel))

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def log_error(self, format, *args):
        # Suppress noisy broken pipe logs when clients disconnect abruptly
        err_msg = format % args
        if any(token in err_msg for token in ["10054", "10053", "Broken pipe", "Connection reset", "Connection aborted"]):
            logger.debug("Client disconnected: %s", err_msg)
        else:
            logger.warning("HTTP Handler Notice: %s", err_msg)

    def _send_json_response(self, data: Any, status_code: int = 200) -> None:
        """Send JSON response with CORS and anti-caching headers."""
        try:
            payload = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def _load_cmdb_summary(self) -> Dict[str, Any]:
        """Read latest CMDB summary from data/cmdb_summary.json or generate dynamically."""
        summary_path = os.path.join(PROJECT_ROOT, "data", "cmdb_summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to read cmdb_summary.json: %s", e)

        # Generate fresh if missing
        try:
            from src.sync.cmdb_generator import CMDBService
            service = CMDBService()
            return service.sync_and_save()
        except Exception as e:
            return {"error": f"Failed to generate CMDB data: {e}", "source": "SolarWinds", "total_configuration_items": 0}

    def do_GET(self):
        """Handle GET requests with read-only REST API routing."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 0. Forward /api/v1 requests to FastAPI backend on port 8000
        if path.startswith("/api/v1/"):
            fastapi_url = f"http://127.0.0.1:8000{self.path}"
            try:
                req = urllib.request.Request(fastapi_url, headers={"User-Agent": "ITOM-Proxy/1.0"})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        payload = resp.read()
                        self.send_response(resp.status)
                        self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                        self.send_header("Content-Length", str(len(payload)))
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                except urllib.error.HTTPError as http_err:
                    payload = http_err.read()
                    self.send_response(http_err.code)
                    self.send_header("Content-Type", http_err.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
            except Exception as e:
                logger.debug("Proxy forward to FastAPI (%s) notice: %s", fastapi_url, e)

        # 1. GET /api/cmdb/summary
        if path == "/api/cmdb/summary":
            summary = self._load_cmdb_summary()
            self._send_json_response(summary)
            return

        # 2. GET /api/cmdb/items
        if path == "/api/cmdb/items":
            summary = self._load_cmdb_summary()
            items = summary.get("sample_devices", [])
            query_params = urllib.parse.parse_qs(parsed_url.query)
            ci_type = query_params.get("type", [None])[0]
            status = query_params.get("status", [None])[0]
            vendor = query_params.get("vendor", [None])[0]

            filtered = items
            if ci_type:
                filtered = [i for i in filtered if i.get("ci_type", "").lower() == ci_type.lower()]
            if status:
                filtered = [i for i in filtered if i.get("status", "").lower() == status.lower()]
            if vendor:
                filtered = [i for i in filtered if i.get("vendor", "").lower() == vendor.lower()]

            self._send_json_response({
                "source": "SolarWinds",
                "mode": summary.get("metadata", {}).get("mode", "live"),
                "total_items": len(filtered),
                "items": filtered
            })
            return

        # 3. GET /api/cmdb/servers
        if path == "/api/cmdb/servers":
            summary = self._load_cmdb_summary()
            items = summary.get("sample_devices", [])
            servers = [i for i in items if i.get("ci_type") == "Server"]
            self._send_json_response({
                "source": "SolarWinds",
                "mode": summary.get("metadata", {}).get("mode", "live"),
                "total_servers": len(servers),
                "servers": servers
            })
            return

        # 4. GET /api/cmdb/network-devices
        if path == "/api/cmdb/network-devices":
            summary = self._load_cmdb_summary()
            items = summary.get("sample_devices", [])
            net_devices = [i for i in items if i.get("ci_type") in ["Access Switch", "Distribution Switch", "Core Switch", "Router", "Firewall", "Wireless Controller", "Network Appliance"]]
            self._send_json_response({
                "source": "SolarWinds",
                "mode": summary.get("metadata", {}).get("mode", "live"),
                "total_network_devices": len(net_devices),
                "network_devices": net_devices
            })
            return

        # 5. GET /api/cmdb/health
        if path == "/api/cmdb/health":
            summary = self._load_cmdb_summary()
            meta = summary.get("metadata", {})
            metrics = summary.get("metrics", {})
            self._send_json_response({
                "status": "healthy" if meta.get("connection_status", "").startswith("Connected") else "degraded",
                "source": "SolarWinds",
                "source_api": meta.get("source_api", "SolarWinds Information Service (SWIS) v3"),
                "mode": meta.get("mode", "live"),
                "connection_status": meta.get("connection_status", "Connected"),
                "last_refreshed": meta.get("generated_at"),
                "total_cis": meta.get("total_configuration_items", 0),
                "active_monitored_cis": meta.get("active_monitored_cis", 0),
                "high_health_cis": metrics.get("high_health_cis", 0),
                "low_health_cis": metrics.get("low_health_cis", 0),
            })
            return

        # Fallback to standard static file serving
        super().do_GET()

    def do_POST(self):
        """Block any write/mutation attempt against SolarWinds CMDB."""
        self._send_json_response({
            "error": "Forbidden: SolarWinds CMDB API is strictly READ-ONLY.",
            "allowed_methods": ["GET"]
        }, status_code=405)

    def do_PUT(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def end_headers(self):
        try:
            self.send_header('Access-Control-Allow-Origin', '*')
            if self.path.endswith('.json') or self.path.endswith('.js') or self.path.endswith('.html'):
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            super().end_headers()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def copyfile(self, source, outputfile):
        """Safely stream files catching socket closure exceptions without crashing."""
        try:
            super().copyfile(source, outputfile)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as e:
            logger.debug("Socket pipe closed during file transfer: %s", e)

    def handle_one_request(self):
        """Handle individual HTTP request wrapped with connection exception guards."""
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
            logger.debug("Client socket closed during request: %s", e)
            self.close_connection = True



def print_server_endpoints(port: int, host: str):
    """Log dynamic access URLs for all active network interfaces."""
    logger.info("================================================================")
    logger.info("  ITOM Enterprise Portal & Analytics Production Web Server")
    logger.info("================================================================")
    logger.info("  Binding Address:   %s:%d", host, port)
    logger.info("  Root Directory:    %s", PROJECT_ROOT)
    logger.info("  Local Access:      http://localhost:%d/", port)
    logger.info("  Local Analytics:   http://localhost:%d/ops_analytics.html", port)
    
    dynamic_ips = get_dynamic_ips()
    for ip in dynamic_ips:
        if ip != "127.0.0.1":
            logger.info("  Network Access:    http://%s:%d/", ip, port)
            logger.info("  Network Analytics: http://%s:%d/ops_analytics.html", ip, port)
    logger.info("================================================================")
def print_status():
    """Print clean formatted status and endpoints for CLI status queries."""
    print("Accessible Endpoints:")
    print(f"  - Localhost Portal:     http://localhost:{PORT}/")
    print(f"  - Localhost Analytics:  http://localhost:{PORT}/ops_analytics.html")
    for ip in get_dynamic_ips():
        if ip != "127.0.0.1":
            print(f"  - Network Access:       http://{ip}:{PORT}/")
            print(f"  - Network Analytics:    http://{ip}:{PORT}/ops_analytics.html")



def run_http_server(stop_event: threading.Event = None):
    """Run resilient HTTP server with automatic port re-binding."""
    server = None
    try:
        server = ThreadingHTTPServer((HOST, PORT), CustomHTTPHandler)
        print_server_endpoints(PORT, HOST)
        
        if stop_event:
            # Polling server loop for clean test stops
            server.timeout = 1.0
            while not stop_event.is_set():
                server.handle_request()
        else:
            server.serve_forever()
    except (OSError, socket.error) as sock_err:
        logger.error("Socket error on %s:%d: %s. Port may be held in TIME_WAIT. Retrying in 3s...", HOST, PORT, sock_err)
        time.sleep(3)
        raise
    except Exception as e:
        logger.error("HTTP Server encountered unexpected error: %s", e)
        raise
    finally:
        if server:
            try:
                server.server_close()
            except Exception:
                pass


def execute_sync():
    """Execute background telemetry sync pipeline with timeout safety."""
    logger.info("=== Starting Scheduled 10-Minute Telemetry Extraction ===")
    try:
        cmd = [sys.executable, SYNC_SCRIPT, "--skip-firestore"]
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("Telemetry sync executed successfully. Datasets refreshed.")
        else:
            logger.warning("Telemetry sync completed with warnings: %s", (result.stderr or result.stdout).strip())
    except subprocess.TimeoutExpired:
        logger.error("Telemetry sync pipeline timed out after 300 seconds. Process terminated.")
    except Exception as err:
        logger.error("Failed to execute sync pipeline: %s", err)


def run_sync_daemon():
    """Continuous background sync thread with self-healing exception loop."""
    logger.info("ITOM 10-Minute Telemetry Sync Daemon started.")
    time.sleep(3)
    execute_sync()
    
    while True:
        try:
            time.sleep(INTERVAL_SECONDS)
            execute_sync()
        except Exception as e:
            logger.error("Sync daemon encountered error: %s", e)
            time.sleep(60)


def setup_signal_handlers():
    """Configure graceful termination signal handlers."""
    def handle_signal(sig, frame):
        logger.info("Received signal %s. Shutting down gracefully...", sig)
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)  # Ignore SIGHUP on Linux to survive SSH disconnects
    except Exception as e:
        logger.debug("Signal handler registration note: %s", e)


def main():
    """Master process supervisor loop."""
    setup_signal_handlers()
    logger.info("Starting ITOM Production Unified Server Supervisor on port %d...", PORT)
    
    sync_thread = threading.Thread(target=run_sync_daemon, daemon=True, name="SyncDaemonThread")
    sync_thread.start()
    
    restart_delay = 3
    while True:
        try:
            run_http_server()
        except KeyboardInterrupt:
            logger.info("Server supervisor stopped by user.")
            break
        except SystemExit:
            logger.info("Server process exiting.")
            break
        except Exception as err:
            logger.error("Server instance terminated: %s. Supervisor auto-restarting in %ds...", err, restart_delay)
            time.sleep(restart_delay)


if __name__ == "__main__":
    main()
