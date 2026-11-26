"""Start a local experimental portal without sharing production databases or sync."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.staging_config import build_staging_environment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-env", required=True)
    parser.add_argument("--experimental-env", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    production_path = Path(args.production_env)
    experimental_path = Path(args.experimental_env)
    if not production_path.is_file() or not experimental_path.is_file():
        print("Both configuration files must exist.", file=sys.stderr)
        return 1
    production = dotenv_values(production_path)
    experimental = dotenv_values(experimental_path)
    try:
        overrides = build_staging_environment(production, experimental.get("DATABASE_URL") or "", ROOT / "data" / "experimental")
    except ValueError as exc:
        print(f"Experimental configuration rejected: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print("Experimental isolation configuration accepted.")
        return 0

    os.environ.update(overrides)
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8081)
    return 0


if __name__ == "__main__":
    sys.exit(main())