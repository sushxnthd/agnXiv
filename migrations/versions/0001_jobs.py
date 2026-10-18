"""Create hosted AgnXiv jobs table."""

import sqlalchemy as sa
from alembic import op

revision = "0001_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agnxiv_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("repository_ref", sa.String(length=255), nullable=False),
        sa.Column("arxiv_id", sa.String(length=64), nullable=True),
        sa.Column("spec_path", sa.String(length=255), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agnxiv_jobs_api_key_hash",
        "agnxiv_jobs",
        ["api_key_hash"],
    )
    op.create_index(
        "ix_agnxiv_jobs_status",
        "agnxiv_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_agnxiv_jobs_status", table_name="agnxiv_jobs")
    op.drop_index("ix_agnxiv_jobs_api_key_hash", table_name="agnxiv_jobs")
    op.drop_table("agnxiv_jobs")
