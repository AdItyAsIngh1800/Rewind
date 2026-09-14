"""record run media.

Revision ID: 5c1e7a9d2b04
Revises: 226601bb67e3
Create Date: 2026-09-14 00:40:00.000000

ADR-0006: a run records the clips it processed and, when known, when its footage was
captured. Both are additive; existing runs get an empty media map, which the replay
reports as "no recorded footage" rather than guessing a path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5c1e7a9d2b04"
down_revision: str | None = "226601bb67e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.add_column(
        "processing_runs",
        sa.Column(
            "media_uris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "processing_runs",
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_column("processing_runs", "captured_at")
    op.drop_column("processing_runs", "media_uris")
