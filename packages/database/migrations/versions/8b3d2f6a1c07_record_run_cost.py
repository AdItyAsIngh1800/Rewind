"""record run cost.

Revision ID: 8b3d2f6a1c07
Revises: 5c1e7a9d2b04
Create Date: 2026-09-15 00:30:00.000000

ADR-0008: a run records the frames it processed, its seconds per stage and its peak
memory. All additive; runs processed before this read as "not recorded", never as zero.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8b3d2f6a1c07"
down_revision: str | None = "5c1e7a9d2b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.add_column("processing_runs", sa.Column("frames_processed", sa.Integer(), nullable=True))
    op.add_column(
        "processing_runs",
        sa.Column(
            "stages_s",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("processing_runs", sa.Column("peak_memory_mb", sa.Float(), nullable=True))


def downgrade() -> None:
    """Revert this migration."""
    op.drop_column("processing_runs", "peak_memory_mb")
    op.drop_column("processing_runs", "stages_s")
    op.drop_column("processing_runs", "frames_processed")
