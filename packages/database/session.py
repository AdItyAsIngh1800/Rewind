"""Database settings and session factory."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "rewind"
    postgres_password: str = "rewind"
    postgres_db: str = "rewind"
    postgres_host: str = "localhost"
    postgres_port: int = 5433  # host-side; 5432 inside the compose network

    @property
    def url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = DatabaseSettings()


def make_engine(url: str | None = None) -> Engine:
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
