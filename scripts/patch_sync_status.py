"""Make GET /api/v1/sync/status report FAILED runs honestly.

THE BUG
-------
`sync_state` was derived from age alone:

    sync_state = "HEALTHY" if age_seconds <= 900 else "DEGRADED"

Whether the run SUCCEEDED was never consulted. A sync that failed in 42ms is
"recent", so the endpoint reported HEALTHY while both sources showed FAILED in
the very same response.

On 11 September that let a total ingestion outage run from 09:16 to 16:00 -
roughly seven hours - with the status endpoint insisting everything was fine.

THE FIX
-------
`sync_state` now weighs status first, then age:

    FAILED    every tracked source's last run failed
    DEGRADED  some sources failed, or data is older than the freshness window
    HEALTHY   recent AND successful
    IDLE      no runs recorded yet

Three fields are added so a dashboard can explain itself:

    healthy_sources / failed_sources   which domains are in which state
    last_successful_sync               when data was genuinely last refreshed,
                                       as opposed to when a sync last ATTEMPTED
    state_reason                       plain-English explanation

`last_sync` keeps its original meaning (last attempt) so existing consumers do
not break.

USAGE
-----
    python scripts/patch_sync_status.py           # preview, changes nothing
    python scripts/patch_sync_status.py --apply   # write the change
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(PROJECT_ROOT, "app", "api", "v1", "endpoints", "sync.py")

# The exact block being replaced - matched verbatim so we fail loudly if the
# file has changed underneath us.
OLD_BLOCK = '''    age_seconds = None
    sync_state = "IDLE"

    if last_sync_time:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - last_sync_time).total_seconds()))
        sync_state = "HEALTHY" if age_seconds <= 900 else "DEGRADED"
'''

NEW_BLOCK = '''    age_seconds = None
    sync_state = "IDLE"
    state_reason = "No synchronization runs recorded yet."

    if last_sync_time:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - last_sync_time).total_seconds()))

    # Status is weighed BEFORE age. A run that fails in 42ms is recent, and the
    # previous implementation called that HEALTHY - which is how a seven-hour
    # ingestion outage went unnoticed on 11 September 2026.
    tracked = {"SOLARWINDS": latest_sw, "INTUNE": latest_intune}
    observed = {name: run for name, run in tracked.items() if run is not None}

    failed_sources = [n for n, r in observed.items() if r.status == "FAILED"]
    healthy_sources = [n for n, r in observed.items() if r.status == "SUCCESS"]

    # When data was genuinely last refreshed, as opposed to last attempted.
    successful_times = [
        (r.completed_at.replace(tzinfo=timezone.utc) if r.completed_at.tzinfo is None else r.completed_at)
        for r in observed.values()
        if r.status == "SUCCESS" and r.completed_at
    ]
    last_successful = max(successful_times) if successful_times else None
    successful_age = (
        max(0, int((now - last_successful).total_seconds())) if last_successful else None
    )

    if observed:
        if failed_sources and not healthy_sources:
            sync_state = "FAILED"
            state_reason = (
                f"All tracked sources failed their most recent run: "
                f"{', '.join(sorted(failed_sources))}."
            )
        elif failed_sources:
            sync_state = "DEGRADED"
            state_reason = (
                f"Partial failure - {', '.join(sorted(failed_sources))} failed; "
                f"{', '.join(sorted(healthy_sources))} succeeded."
            )
        elif successful_age is not None and successful_age > 900:
            sync_state = "DEGRADED"
            state_reason = (
                f"All sources succeeded, but the newest data is "
                f"{successful_age}s old (threshold 900s)."
            )
        else:
            sync_state = "HEALTHY"
            state_reason = "All tracked sources synchronized successfully and recently."
'''

OLD_RETURN = '''        "last_sync": last_sync_time.isoformat() if last_sync_time else None,'''

NEW_RETURN = '''        "state_reason": state_reason,
        "last_sync": last_sync_time.isoformat() if last_sync_time else None,
        "last_successful_sync": last_successful.isoformat() if last_successful else None,
        "successful_age_seconds": successful_age,
        "healthy_sources": sorted(healthy_sources),
        "failed_sources": sorted(failed_sources),'''


def fail(message: str) -> int:
    print(f"\n  STOPPED: {message}")
    print("  No changes were made.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix the dishonest sync_state")
    parser.add_argument("--apply", action="store_true", help="Write the change")
    args = parser.parse_args()

    print()
    print("=" * 70)
    print("PATCH: /sync/status must report FAILED runs honestly")
    print("=" * 70)
    print(f"  Target: {TARGET}")

    if not os.path.exists(TARGET):
        return fail(f"Not found: {TARGET}")

    with open(TARGET, "r", encoding="utf-8") as handle:
        source = handle.read()

    if "state_reason" in source:
        print("\n  Already patched. Nothing to do.")
        return 0

    if OLD_BLOCK not in source:
        return fail(
            "The sync_state block does not match what was expected.\n"
            "           The file has changed - apply the fix by hand."
        )

    if OLD_RETURN not in source:
        return fail("The return block does not match what was expected.")

    patched = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
    patched = patched.replace(OLD_RETURN, NEW_RETURN, 1)

    added = len(patched.splitlines()) - len(source.splitlines())
    print("\n  [1/2] sync_state logic  -> status weighed before age")
    print("  [2/2] response fields   -> + state_reason, last_successful_sync,")
    print("                              successful_age_seconds, healthy_sources,")
    print("                              failed_sources")
    print(f"\n  Net change: +{added} lines")
    print("""
  Behaviour change:
    before  all sources FAILED  -> "HEALTHY"   (recent, so assumed fine)
    after   all sources FAILED  -> "FAILED"    (with a reason)
""")

    if not args.apply:
        print("  PREVIEW ONLY - nothing written.")
        print("  Run again with --apply to make the change.")
        return 0

    backup = TARGET + ".bak"
    shutil.copy2(TARGET, backup)
    print(f"  Backup written: {os.path.basename(backup)}")

    with open(TARGET, "w", encoding="utf-8") as handle:
        handle.write(patched)

    import py_compile
    try:
        py_compile.compile(TARGET, doraise=True)
        print("  Syntax OK. sync.py updated.")
    except py_compile.PyCompileError as exc:
        shutil.copy2(backup, TARGET)
        return fail(f"Patched file failed to compile, original restored.\n           {exc}")

    print("""
  NEXT STEPS

    1. Restart the server, then:
         curl.exe http://localhost:8000/api/v1/sync/status

    2. Confirm sync_state reflects the per-source statuses below it.

    3. Commit:
         git add -A
         git commit -m "Fix: /sync/status no longer reports HEALTHY when syncs fail"
         git push
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
