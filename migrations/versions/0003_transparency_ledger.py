"""Create the append-only verification transparency ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0003_transparency_ledger"
down_revision = "0002_job_idempotency"
branch_labels = None
depends_on = None

GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.create_table(
        "agnxiv_transparency_head",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agnxiv_transparency_entries",
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("repository_ref", sa.String(length=255), nullable=False),
        sa.Column("arxiv_id", sa.String(length=64), nullable=True),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("sequence"),
        sa.UniqueConstraint("entry_hash"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        "ix_agnxiv_transparency_entries_job_id",
        "agnxiv_transparency_entries",
        ["job_id"],
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO agnxiv_transparency_head "
            "(id, sequence, head_hash) VALUES (1, 0, :genesis)"
        ),
        {"genesis": GENESIS_HASH},
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION agnxiv_block_transparency_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'agnxiv transparency ledger is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER agnxiv_transparency_no_mutation
            BEFORE UPDATE OR DELETE ON agnxiv_transparency_entries
            FOR EACH ROW
            EXECUTE FUNCTION agnxiv_block_transparency_mutation()
            """
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER agnxiv_transparency_no_update
            BEFORE UPDATE ON agnxiv_transparency_entries
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'agnxiv transparency ledger is append-only'
                );
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER agnxiv_transparency_no_delete
            BEFORE DELETE ON agnxiv_transparency_entries
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'agnxiv transparency ledger is append-only'
                );
            END
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS agnxiv_transparency_no_mutation "
            "ON agnxiv_transparency_entries"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS agnxiv_block_transparency_mutation()"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS agnxiv_transparency_no_update")
        op.execute("DROP TRIGGER IF EXISTS agnxiv_transparency_no_delete")

    op.drop_index(
        "ix_agnxiv_transparency_entries_job_id",
        table_name="agnxiv_transparency_entries",
    )
    op.drop_table("agnxiv_transparency_entries")
    op.drop_table("agnxiv_transparency_head")
