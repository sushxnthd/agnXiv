"""Bind hosted jobs to exact GitHub Actions workflow runs."""

import sqlalchemy as sa
from alembic import op

revision = "0004_workflow_run_binding"
down_revision = "0003_transparency_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agnxiv_jobs",
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_agnxiv_jobs_workflow_run_id",
        "agnxiv_jobs",
        ["workflow_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agnxiv_jobs_workflow_run_id",
        table_name="agnxiv_jobs",
    )
    op.drop_column("agnxiv_jobs", "workflow_run_id")
