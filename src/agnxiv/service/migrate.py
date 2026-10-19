from __future__ import annotations

import os
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_MIGRATION_LOCK_ID = 6_054_719_943_018_021_947


class MigrationLockError(RuntimeError):
    """The production schema migration lock could not be acquired safely."""


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///./agnxiv-service.db")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def _upgrade() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def migrate() -> None:
    """Upgrade schema once across concurrent service replicas."""
    database_url = _database_url()
    if not database_url.startswith("postgresql+"):
        _upgrade()
        return

    timeout = min(
        600.0,
        max(
            5.0,
            float(os.getenv("AGNXIV_MIGRATION_LOCK_TIMEOUT_SECONDS", "120")),
        ),
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    deadline = time.monotonic() + timeout

    with engine.connect() as connection:
        acquired = False
        try:
            while time.monotonic() < deadline:
                acquired = bool(
                    connection.scalar(
                        text("SELECT pg_try_advisory_lock(:lock_id)"),
                        {"lock_id": _MIGRATION_LOCK_ID},
                    )
                )
                if acquired:
                    break
                time.sleep(1.0)
            if not acquired:
                raise MigrationLockError(
                    f"schema migration lock was not acquired within {timeout:.0f}s"
                )
            _upgrade()
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _MIGRATION_LOCK_ID},
                )
            connection.close()
    engine.dispose()


def main() -> None:
    migrate()


if __name__ == "__main__":
    main()
