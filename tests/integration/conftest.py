"""Shared fixtures for integration tests.

These need a real PostgreSQL because the models use JSONB. The fixture requires an
explicit ``DATABASE_URL`` and deliberately does **not** fall back to the configured
Supabase connection: a test suite that silently pointed at the project's real
database would create and mutate rows in it.

The schema is built with Alembic, not ``Base.metadata.create_all``. The two build
from different sources, and a migration that is wrong while the model is right must
fail here rather than in production.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.main import app
from packages.database.session import get_session

DATABASE_URL = os.environ.get("DATABASE_URL", "")

needs_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set DATABASE_URL to an ephemeral Postgres; it never falls back to Supabase",
)


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Bring the test database up to head using Alembic, once per session."""
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade failed:\n{result.stderr}")
    return DATABASE_URL


@pytest.fixture
def session(migrated_database: str) -> Iterator[Session]:
    """Give each test an isolated session that is rolled back afterwards."""
    engine = create_engine(migrated_database, future=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection)
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """Build an API client whose requests share the test's rolled-back session."""
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous
