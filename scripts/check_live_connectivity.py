"""PRE-FLIGHT: verify live credentials and connectivity WITHOUT writing anything.

Run this BEFORE attempting a real sync. It answers one question per source:

    "Can we authenticate and retrieve data right now?"

It performs READ-ONLY calls and writes nothing to the database or to disk.
A small sample is fetched so a failure surfaces in seconds rather than after a
full 27,000-device extraction.

Usage:
    python scripts/check_live_connectivity.py
    python scripts/check_live_connectivity.py --source intune
    python scripts/check_live_connectivity.py --source solarwinds
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

# Make the project root importable when run from anywhere.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    print("[warn] python-dotenv not installed; relying on ambient environment")


def _mask(value: str | None) -> str:
    """Show only enough of a secret to confirm it is present and non-empty."""
    if not value:
        return "<MISSING>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]} (len={len(value)})"


def banner(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def check_env() -> bool:
    """Report which credentials are present. Never prints a full secret."""
    banner("STEP 1 — Environment / credential presence")

    required = {
        "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID"),
        "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID"),
        "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET"),
        "SOLARWINDS_HOST": os.getenv("SOLARWINDS_HOST"),
        "SOLARWINDS_USERNAME": os.getenv("SOLARWINDS_USERNAME"),
        "SOLARWINDS_PASSWORD": os.getenv("SOLARWINDS_PASSWORD"),
    }

    ok = True
    for key, value in required.items():
        secret = "SECRET" in key or "PASSWORD" in key
        shown = _mask(value) if secret else (value or "<MISSING>")
        state = "OK " if value else "MISS"
        if not value:
            ok = False
        print(f"  [{state}] {key:24} = {shown}")

    print(f"\n  DATABASE_URL configured: {'yes' if os.getenv('DATABASE_URL') else 'no (using default)'}")
    return ok


def check_intune() -> bool:
    """Authenticate against Microsoft Graph and fetch a 5-device sample."""
    banner("STEP 2 — Microsoft Graph (Intune)")

    try:
        from src.sync.graph_client import GraphClient
    except Exception as exc:
        print(f"  [FAIL] Could not import GraphClient: {exc}")
        return False

    client = GraphClient()

    print("  -> Requesting OAuth 2.0 token from Azure AD ...")
    started = time.time()
    try:
        token = client.get_access_token()
        print(f"  [OK ] Token acquired in {time.time() - started:.2f}s "
              f"(length {len(token)})")
    except Exception as exc:
        print(f"  [FAIL] Authentication failed: {exc}")
        print("\n  Common causes:")
        print("    401/invalid_client  -> client secret expired or wrong")
        print("    AADSTS700016        -> application not found in tenant")
        print("    Network error       -> proxy or firewall blocking login.microsoftonline.com")
        return False

    print("  -> Fetching a 5-device sample ...")
    started = time.time()
    try:
        devices = client.fetch_managed_devices(max_devices=5)
    except Exception as exc:
        print(f"  [FAIL] Device query failed: {exc}")
        print("\n  Most likely: the app registration lacks")
        print("    DeviceManagementManagedDevices.Read.All (application permission)")
        print("    or admin consent has not been granted.")
        return False

    print(f"  [OK ] Retrieved {len(devices)} devices in {time.time() - started:.2f}s")

    if devices:
        sample = devices[0]
        print("\n  Sample record (field presence check):")
        for field in ("id", "deviceName", "operatingSystem", "complianceState",
                      "manufacturer", "totalStorageSpaceInBytes"):
            value = sample.get(field)
            marker = "OK " if value not in (None, "") else "NULL"
            display = str(value)[:40] if value not in (None, "") else "<null>"
            print(f"    [{marker}] {field:26} = {display}")

    return True


def check_solarwinds() -> bool:
    """Authenticate against SWIS and run a minimal read-only SWQL query."""
    banner("STEP 3 — SolarWinds Orion (SWIS v3)")

    try:
        from src.sync.solarwinds_client import SolarWindsClient
    except Exception as exc:
        print(f"  [FAIL] Could not import SolarWindsClient: {exc}")
        return False

    client = SolarWindsClient()
    print(f"  Endpoint: {client.base_url}")

    print("  -> Running a minimal read-only SWQL query ...")
    started = time.time()
    try:
        rows = client.query("SELECT TOP 5 n.NodeID, n.Caption, n.Status FROM Orion.Nodes n")
    except Exception as exc:
        print(f"  [FAIL] Query failed: {exc}")
        print("\n  Common causes:")
        print("    401       -> SWIS username or password rejected")
        print("    timeout   -> host unreachable from this machine / VPN required")
        print("    SSL error -> certificate chain not trusted")
        return False

    print(f"  [OK ] Retrieved {len(rows)} rows in {time.time() - started:.2f}s")
    for row in rows[:5]:
        print(f"    NodeID={row.get('NodeID'):<8} "
              f"Status={row.get('Status'):<4} "
              f"Caption={str(row.get('Caption'))[:38]}")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Live connectivity pre-flight (read-only)")
    parser.add_argument("--source", choices=["intune", "solarwinds", "all"], default="all")
    args = parser.parse_args()

    print("\nITOM PORTAL — LIVE CONNECTIVITY PRE-FLIGHT")
    print("Read-only. No database writes. No files modified.")

    env_ok = check_env()
    if not env_ok:
        print("\n  [warn] Some credentials are missing; the affected source will fail.")

    results: dict[str, bool] = {}

    if args.source in ("intune", "all"):
        try:
            results["INTUNE"] = check_intune()
        except Exception:
            traceback.print_exc()
            results["INTUNE"] = False

    if args.source in ("solarwinds", "all"):
        try:
            results["SOLARWINDS"] = check_solarwinds()
        except Exception:
            traceback.print_exc()
            results["SOLARWINDS"] = False

    banner("RESULT")
    for name, ok in results.items():
        print(f"  {name:12} {'REACHABLE' if ok else 'NOT REACHABLE'}")

    if all(results.values()):
        print("\n  All checked sources are reachable.")
        print("  Next: python scripts/run_live_sync.py --source <name>")
        return 0

    print("\n  At least one source is not reachable. Resolve before running a sync.")
    print("  A sync against an unreachable source will correctly record status FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
