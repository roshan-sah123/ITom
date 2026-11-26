"""Initialize an independent loopback PostgreSQL cluster for local experiments."""

import asyncio
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.staging_config import build_staging_environment

DATA = ROOT / "data" / "experimental"
PGDATA = DATA / "postgres"
PRODUCTION_ENV = Path(r"C:\ProgramData\ITOM\app\.env")
PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
PORT = 55432


async def create_databases(url: URL) -> None:
    import asyncpg

    connection = await asyncpg.connect(url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False))
    try:
        await connection.execute('CREATE DATABASE "itom_experimental"')
        await connection.execute('CREATE DATABASE "itom_experimental_modules"')
    finally:
        await connection.close()


def main() -> int:
    config_path = DATA / ".env"
    if PGDATA.exists() or config_path.exists():
        print("Experimental data or configuration already exists; refusing to overwrite.", file=sys.stderr)
        return 1
    if not PRODUCTION_ENV.is_file() or not (PG_BIN / "initdb.exe").is_file():
        print("Production configuration or PostgreSQL binaries unavailable.", file=sys.stderr)
        return 1
    with socket.socket() as listener:
        if listener.connect_ex(("127.0.0.1", PORT)) == 0:
            print("Experimental PostgreSQL port is already in use.", file=sys.stderr)
            return 1

    password = secrets.token_urlsafe(32)
    primary = URL.create("postgresql+asyncpg", username="itom_experimental", password=password,
                         host="127.0.0.1", port=PORT, database="itom_experimental")
    module = primary.set(database="itom_experimental_modules")
    primary_url = primary.render_as_string(hide_password=False)
    module_url = module.render_as_string(hide_password=False)
    try:
        overrides = build_staging_environment(dotenv_values(PRODUCTION_ENV), primary_url, module_url, DATA)
    except ValueError as exc:
        print(f"Experimental configuration rejected: {exc}", file=sys.stderr)
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    password_file = DATA / ".pg-init-password"
    password_file.write_text(password, encoding="utf-8")
    try:
        subprocess.run([str(PG_BIN / "initdb.exe"), "-D", str(PGDATA), "-U", "itom_experimental",
                        "--auth=scram-sha-256", "--pwfile", str(password_file), "--encoding=UTF8", "--no-locale"], check=True)
    finally:
        password_file.unlink(missing_ok=True)

    config_path.write_text(f"DATABASE_URL={primary_url}\nDATABASE_URL_2={module_url}\n", encoding="utf-8")
    subprocess.run([str(PG_BIN / "pg_ctl.exe"), "-D", str(PGDATA), "-l", str(DATA / "postgres.log"),
                    "-o", f"-h 127.0.0.1 -p {PORT}", "-w", "start"], check=True)
    asyncio.run(create_databases(primary))
    environment = os.environ.copy()
    environment.update(overrides)
    for config in ("alembic.ini", "alembic-modules.ini"):
        subprocess.run([sys.executable, "-m", "alembic", "-c", config, "upgrade", "head"],
                       cwd=ROOT, env=environment, check=True)
    print("Independent experimental PostgreSQL databases initialized on 127.0.0.1:55432.")
    return 0


if __name__ == "__main__":
    sys.exit(main())