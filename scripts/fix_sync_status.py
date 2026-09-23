"""Make GET /api/v1/sync/status report FAILED runs honestly.

THE BUG
-------
    sync_state = "HEALTHY" if age_seconds <= 900 else "DEGRADED"

Age alone decided the verdict; whether the run SUCCEEDED was never consulted.
A sync that failed in 42ms is recent, so the endpoint reported HEALTHY while
the same response showed both sources FAILED.

On 11 September 2026 that hid a total ingestion outage from 09:16 to 16:00.

WHY THIS VERSION WORKS WHERE THE LAST ONE DID NOT
-------------------------------------------------
The previous patch matched a multi-line block and failed on Windows CRLF line
endings. This one works line by line and preserves whatever endings the file
already uses.

USAGE
-----
    python scripts/fix_sync_status.py           # preview
    python scripts/fix_sync_status.py --apply   # write
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(PROJECT_ROOT, "app", "api", "v1", "endpoints", "sync.py")

# Anchors, matched after stripping whitespace so indentation cannot break them.
ANCHOR_IDLE = 'sync_state = "IDLE"'
ANCHOR_HEALTHY = 'sync_state = "HEALTHY" if age_seconds <= 900 else "DEGRADED"'
ANCHOR_RETURN = '"sync_state": sync_state,'

# Inserted after `sync_state = "IDLE"` so the names always exist, even when no
# sync has ever run.
IDLE_EXTRA = [
    'state_reason = "No synchronization runs recorded yet."',
    "failed_sources = []",
    "healthy_sources = []",
]

# Replaces the age-only verdict. Status is weighed first.
VERDICT = [
    '_tracked = {"SOLARWINDS": latest_sw, "INTUNE": latest_intune}',
    "_seen = {n: r for n, r in _tracked.items() if r is not None}",
    'failed_sources = sorted(n for n, r in _seen.items() if r.status == "FAILED")',
    'healthy_sources = sorted(n for n, r in _seen.items() if r.status == "SUCCESS")',
    "",
    "if failed_sources and not healthy_sources:",
    '    sync_state = "FAILED"',
    '    state_reason = f"All tracked sources failed: {\', \'.join(failed_sources)}."',
    "elif failed_sources:",
    '    sync_state = "DEGRADED"',
    '    state_reason = f"Partial failure - {\', \'.join(failed_sources)} failed."',
    "elif age_seconds is not None and age_seconds > 900:",
    '    sync_state = "DEGRADED"',
    '    state_reason = f"Sources succeeded, but data is {age_seconds}s old."',
    "else:",
    '    sync_state = "HEALTHY"',
    '    state_reason = "All tracked sources synchronized successfully and recently."',
]

RETURN_EXTRA = [
    '"state_reason": state_reason,',
    '"healthy_sources": healthy_sources,',
    '"failed_sources": failed_sources,',
]


def indent_of(line: str) -> str:
    """Leading whitespace of a line, preserved verbatim."""
    return line[: len(line) - len(line.lstrip())]


def fail(message: str) -> int:
    print(f"\n  STOPPED: {message}")
    print("  No changes were made.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix the dishonest sync_state")
    parser.add_argument("--apply", action="store_true", help="Write the change")
    args = parser.parse_args()

    print()
    print("=" * 66)
    print("FIX: /sync/status must not report HEALTHY when syncs fail")
    print("=" * 66)
    print(f"  Target: {TARGET}")

    if not os.path.exists(TARGET):
        return fail(f"Not found: {TARGET}")

    # newline="" preserves the file's existing line endings on write.
    with open(TARGET, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()

    if "state_reason" in raw:
        print("\n  Already patched. Nothing to do.")
        return 0

    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(newline)
    print(f"  Line endings detected: {'CRLF (Windows)' if newline == chr(13)+chr(10) else 'LF (Unix)'}")

    idx_idle = idx_healthy = idx_return = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == ANCHOR_IDLE and idx_idle is None:
            idx_idle = i
        elif stripped == ANCHOR_HEALTHY and idx_healthy is None:
            idx_healthy = i
        elif stripped == ANCHOR_RETURN and idx_return is None:
            idx_return = i

    missing = []
    if idx_idle is None:
        missing.append(ANCHOR_IDLE)
    if idx_healthy is None:
        missing.append(ANCHOR_HEALTHY)
    if idx_return is None:
        missing.append(ANCHOR_RETURN)
    if missing:
        return fail("Could not locate:\n           " + "\n           ".join(missing))

    print(f"\n  Found anchors at lines {idx_idle + 1}, {idx_healthy + 1}, {idx_return + 1}")

    # Apply from the bottom up so earlier indices stay valid.
    out = list(lines)

    pad = indent_of(out[idx_return])
    out[idx_return + 1 : idx_return + 1] = [pad + s for s in RETURN_EXTRA]
    print("  [3/3] return block  -> + state_reason, healthy_sources, failed_sources")

    pad = indent_of(out[idx_healthy])
    out[idx_healthy : idx_healthy + 1] = [(pad + s if s else "") for s in VERDICT]
    print("  [2/3] verdict       -> status weighed before age")

    pad = indent_of(out[idx_idle])
    out[idx_idle + 1 : idx_idle + 1] = [pad + s for s in IDLE_EXTRA]
    print("  [1/3] defaults      -> names defined for the no-runs case")

    patched = newline.join(out)
    print(f"\n  Net change: +{len(out) - len(lines)} lines")
    print("""
  Behaviour:
    both sources FAILED   ->  FAILED     (was HEALTHY)
    one failed, one ok    ->  DEGRADED   (was HEALTHY)
    all ok, data stale    ->  DEGRADED
    all ok, data recent   ->  HEALTHY
""")

    if not args.apply:
        print("  PREVIEW ONLY - nothing written.")
        print("  Run again with --apply to make the change.")
        return 0

    backup = TARGET + ".bak"
    shutil.copy2(TARGET, backup)
    print(f"  Backup: {os.path.basename(backup)}")

    with open(TARGET, "w", encoding="utf-8", newline="") as handle:
        handle.write(patched)

    import py_compile
    try:
        py_compile.compile(TARGET, doraise=True)
        print("  Syntax OK. sync.py updated.")
    except py_compile.PyCompileError as exc:
        shutil.copy2(backup, TARGET)
        return fail(f"Failed to compile, original restored.\n           {exc}")

    print("""
  NEXT

    1. Restart the server, then:
         curl.exe http://localhost:8000/api/v1/sync/status

    2. Look for the new state_reason field.

    3. Commit:
         git add -A
         git commit -m "Fix: /sync/status reports FAILED runs honestly"
         git push
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
