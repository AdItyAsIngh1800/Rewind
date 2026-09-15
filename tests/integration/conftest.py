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
import pathlib
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.main import app
from packages.database.models import Camera, ProcessingRun
from packages.database.session import get_session
from packages.schemas import RunStatus
from tests.accounts import INVESTIGATOR

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
    # Savepoints, so the code under test commits and rolls back as it does in production
    # while the outer transaction still discards everything at teardown.
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
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
        yield TestClient(app, headers=INVESTIGATOR)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous


#: case_01 and deliberately wrong offsets, shared by the pipeline and failure tests.
#: The clips are frame-synchronous (scene spec §4.1), so these shift CAM_B and CAM_C off
#: the true clock by exactly these amounts; test_pipeline asserts E5.1 catches it.
CASE_DIR = pathlib.Path("data/samples/case_01")
OFFSETS = {"CAM_A": 0.0, "CAM_B": 0.4, "CAM_C": -0.2}


@pytest.fixture
def queued_run(session: Session) -> ProcessingRun:
    """Create a queued run with its cameras registered."""
    if not any(CASE_DIR.glob("*.mp4")):
        pytest.skip("case_01 video has not been rendered")
    for camera_id in OFFSETS:
        session.add(
            Camera(
                camera_id=camera_id,
                name=camera_id,
                source_uri="file:///x",
                clock_offset_s=OFFSETS[camera_id],
                width=1280,
                height=720,
                fps=10.0,
            )
        )
    run = ProcessingRun(
        run_id="run-pipeline-test",
        input_hash="sha256:t",
        dataset_version="v1",
        config_version="t",
        status=RunStatus.QUEUED.value,
    )
    session.add(run)
    session.flush()
    return run
