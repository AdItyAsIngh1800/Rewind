"""Database settings and session factory (Supabase).

Connections go through the Supavisor **session pooler**, never the direct
`db.<ref>.supabase.co` endpoint. See ADR-0003 — the direct endpoint is IPv6-only on
projects created after early 2024 and fails on IPv4-only networks with an opaque
timeout rather than a useful error.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSettings(BaseSettings):
    """Database connection settings, read from the environment and ``.env``.

    Credentials never live in the repository. ``DATABASE_URL`` exists as an escape
    hatch so CI can point at an ephemeral Postgres without Supabase credentials.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_project_ref: str = ""
    supabase_region: str = "ap-southeast-1"
    supabase_db_password: str = ""
    supabase_db_user: str = "postgres"
    supabase_db_name: str = "postgres"

    #: Full DSN override. Used by CI, which runs integration tests against an
    #: ephemeral postgres service container rather than against Supabase.
    database_url: str = ""

    @property
    def url(self) -> str:
        """Build the SQLAlchemy DSN, preferring an explicit override when set.

        Raises:
            RuntimeError: if neither an override nor Supabase credentials are set.

        """
        if self.database_url:
            return self.database_url
        if not self.supabase_project_ref or not self.supabase_db_password:
            raise RuntimeError(
                "No database configured. Set SUPABASE_PROJECT_REF and "
                "SUPABASE_DB_PASSWORD in .env (see .env.example), or set "
                "DATABASE_URL to point at a plain Postgres instance."
            )
        # Session mode (5432), not transaction mode (6543): session mode supports
        # prepared statements, which Alembic DDL and SQLAlchemy's defaults rely on.
        host = f"aws-0-{self.supabase_region}.pooler.supabase.com"
        user = f"{self.supabase_db_user}.{self.supabase_project_ref}"
        return (
            f"postgresql+psycopg://{quote(user)}:{quote(self.supabase_db_password)}"
            f"@{host}:5432/{self.supabase_db_name}"
        )

    @property
    def safe_url(self) -> str:
        """The DSN with the password removed, for logging."""
        url = self.url
        if "@" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"


settings = DatabaseSettings()


def make_engine(url: str | None = None) -> Engine:
    """Create an engine, defaulting to the configured DSN.

    ``pool_pre_ping`` matters against a hosted database: a pooled connection can be
    closed server-side between requests, and pre-ping turns that into a transparent
    reconnect rather than an error on the next query.
    """
    return create_engine(url or settings.url, pool_pre_ping=True, future=True)


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session."""
    global _engine, _factory
    if _factory is None:
        _engine = make_engine()
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    with _factory() as session:
        yield session
