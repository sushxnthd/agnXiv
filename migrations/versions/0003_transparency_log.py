"""Add tamper-evident hosted transparency log."""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0003_transparency_log"
down_revision = "0002_job_idempotency"
branch_labels = None
depends_on = None

_ZERO_HASH = "0" * 64


def upgrade() -> None:
    op.create_table(
        "agnxiv_transparency_head",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agnxiv_transparency_entries",
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sequence"),
        sa.UniqueConstraint("entry_hash"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        "ix_agnxiv_transparency_entries_job_id",
        "agnxiv_transparency_entries",
        ["job_id"],
    )
    head = sa.table(
        "agnxiv_transparency_head",
        sa.column("id", sa.Integer()),
        sa.column("sequence", sa.Integer()),
        sa.column("entry_hash", sa.String()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        head,
        [
            {
                "id": 1,
                "sequence": 0,
                "entry_hash": _ZERO_HASH,
                "updated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agnxiv_transparency_entries_job_id",
        table_name="agnxiv_transparency_entries",
    )
    op.drop_table("agnxiv_transparency_entries")
    op.drop_table("agnxiv_transparency_head")
