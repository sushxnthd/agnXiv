"""Add idempotent hosted job submission."""

import sqlalchemy as sa
from alembic import op

revision = "0002_job_idempotency"
down_revision = "0001_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agnxiv_jobs",
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agnxiv_jobs",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_agnxiv_jobs_idempotency_key_hash",
        "agnxiv_jobs",
        ["idempotency_key_hash"],
    )
    op.create_index(
        "uq_agnxiv_jobs_api_idempotency",
        "agnxiv_jobs",
        ["api_key_hash", "idempotency_key_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agnxiv_jobs_api_idempotency",
        table_name="agnxiv_jobs",
    )
    op.drop_index(
        "ix_agnxiv_jobs_idempotency_key_hash",
        table_name="agnxiv_jobs",
    )
    op.drop_column("agnxiv_jobs", "request_fingerprint")
    op.drop_column("agnxiv_jobs", "idempotency_key_hash")
