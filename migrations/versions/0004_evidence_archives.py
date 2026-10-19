"""Add append-only evidence archives and publication registry metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_evidence_archives"
down_revision = "0003_transparency_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agnxiv_jobs",
        sa.Column("doi", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "agnxiv_jobs",
        sa.Column("publication_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "agnxiv_evidence_archives",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("transparency_sequence", sa.Integer(), nullable=False),
        sa.Column("transparency_entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("retain_until", sa.String(length=40), nullable=False),
        sa.Column("retention_policy", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("content_sha256"),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION agnxiv_block_evidence_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'agnxiv evidence archive is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER agnxiv_evidence_no_mutation
            BEFORE UPDATE OR DELETE ON agnxiv_evidence_archives
            FOR EACH ROW
            EXECUTE FUNCTION agnxiv_block_evidence_mutation()
            """
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER agnxiv_evidence_no_update
            BEFORE UPDATE ON agnxiv_evidence_archives
            BEGIN
                SELECT RAISE(ABORT, 'agnxiv evidence archive is append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER agnxiv_evidence_no_delete
            BEFORE DELETE ON agnxiv_evidence_archives
            BEGIN
                SELECT RAISE(ABORT, 'agnxiv evidence archive is append-only');
            END
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS agnxiv_evidence_no_mutation "
            "ON agnxiv_evidence_archives"
        )
        op.execute("DROP FUNCTION IF EXISTS agnxiv_block_evidence_mutation()")
    elif bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS agnxiv_evidence_no_update")
        op.execute("DROP TRIGGER IF EXISTS agnxiv_evidence_no_delete")

    op.drop_table("agnxiv_evidence_archives")
    op.drop_column("agnxiv_jobs", "publication_json")
    op.drop_column("agnxiv_jobs", "doi")
