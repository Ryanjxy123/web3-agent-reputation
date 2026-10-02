"""Every test owns a fresh PostgreSQL database, never truncates the user's database."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from reputation_platform.infrastructure.db.connection import database_url, engine, repo_root
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def db(monkeypatch):
    configured = make_url(database_url())
    name = "reputation_test_" + uuid4().hex
    admin = create_engine(
        configured.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = configured.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", test_url)
    database = engine(test_url)
    try:
        command.upgrade(Config(str(repo_root() / "alembic.ini")), "head")
        yield database
    finally:
        database.dispose()
        # Name is internally generated and refers exclusively to this fixture's database.
        assert name.startswith("reputation_test_") and len(name) == len("reputation_test_") + 32
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
