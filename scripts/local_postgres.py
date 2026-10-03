"""Run a project-local PostgreSQL instance without services or global configuration."""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
WINDOWS_RUNTIME = Path(ROOT.anchor) / "web3-runtime"
DATA = RUNTIME / "postgres"
CONFIG = RUNTIME / "local-db.json"


def runtime_alias() -> Path:
    """Postgres' Windows native startup embeds ANSI paths in UTF-8 SQL.

    Use an ASCII directory junction for runtime; no checkout is copied/moved.
    """
    if os.name != "nt":
        return RUNTIME
    alias = WINDOWS_RUNTIME
    if not str(alias).isascii():
        raise RuntimeError("PostgreSQL runtime junction must have an ASCII path")
    if not os.path.lexists(alias):
        RUNTIME.mkdir(exist_ok=True)
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(RUNTIME)],
            check=True,
            capture_output=True,
        )
    if not alias.exists() or not alias.samefile(RUNTIME):
        raise RuntimeError("PostgreSQL runtime junction belongs to another directory")
    return alias


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "start", "stop", "status"])
    args = parser.parse_args()
    alias = runtime_alias()
    binary = alias / "tools/postgresql-17.11/pgsql/bin"
    data_path = alias / "postgres"
    pg_ctl = str(binary / "pg_ctl.exe")
    if args.command == "init":
        if (DATA / "PG_VERSION").exists():
            print("Existing PostgreSQL cluster preserved.")
            return 0
        RUNTIME.mkdir(exist_ok=True)
        if CONFIG.exists():
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
        else:
            password = secrets.token_urlsafe(32)
            config = {
                "host": "127.0.0.1",
                "port": 55432,
                "user": "postgres",
                "password": password,
                "database": "reputation",
                "url": f"postgresql+psycopg://postgres:{password}@127.0.0.1:55432/reputation",
            }
            with CONFIG.open("x", encoding="utf-8") as handle:
                json.dump(config, handle)
        password_file = RUNTIME / "postgres-init.password"
        password_file.write_text(config["password"], encoding="utf-8")
        try:
            subprocess.run(
                [
                    str(binary / "initdb.exe"),
                    "-D",
                    str(data_path),
                    "-U",
                    "postgres",
                    "--encoding=UTF8",
                    "--locale=C",
                    "--auth=scram-sha-256",
                    f"--pwfile={alias / password_file.name}",
                ],
                check=True,
            )
        finally:
            password_file.unlink(missing_ok=True)
        print("Initialized local cluster; credentials are stored only in ignored runtime.")
        return 0
    if args.command == "start":
        status = subprocess.run([pg_ctl, "-D", str(data_path), "status"], capture_output=True)
        if status.returncode:
            subprocess.run(
                [
                    pg_ctl,
                    "-D",
                    str(data_path),
                    "-l",
                    str(alias / "postgres.log"),
                    "-o",
                    "-h 127.0.0.1 -p 55432 -c timezone=UTC",
                    "-w",
                    "start",
                ],
                check=True,
            )
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        import psycopg

        with psycopg.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            dbname="postgres",
            autocommit=True,
        ) as conn:
            if not conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (config["database"],)
            ).fetchone():
                from psycopg import sql

                conn.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config["database"]))
                )
        print("PostgreSQL ready on loopback port 55432.")
        return 0
    if args.command == "stop":
        return subprocess.run([pg_ctl, "-D", str(data_path), "-m", "fast", "-w", "stop"]).returncode
    return subprocess.run([pg_ctl, "-D", str(data_path), "status"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
