"""Engine configuration; never logs database credentials."""

import json
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine


def repo_root() -> Path:
    if configured := os.environ.get("REPUTATION_ROOT"):
        return Path(configured).resolve()
    for parent in (Path.cwd(), *Path(__file__).resolve().parents):
        if (parent / "pyproject.toml").exists() and (parent / "AGENTS.md").exists():
            return parent
    raise RuntimeError("Set REPUTATION_ROOT to the project directory")


def database_url() -> str:
    if value := os.environ.get("DATABASE_URL"):
        return value
    local = repo_root() / "runtime/local-db.json"
    if local.exists():
        return str(json.loads(local.read_text(encoding="utf-8"))["url"])
    raise RuntimeError("DATABASE_URL is not configured")


def engine(url: str | None = None) -> Engine:
    value = url or database_url()
    if not value.startswith("postgresql+psycopg://"):
        raise ValueError("Only PostgreSQL with psycopg is supported")
    return create_engine(
        value, pool_pre_ping=True, hide_parameters=True, connect_args={"options": "-c timezone=UTC"}
    )
