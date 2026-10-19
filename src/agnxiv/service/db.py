from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from ..transparency import GENESIS_HASH, compute_entry_hash, digest_json


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "agnxiv_jobs"
    __table_args__ = (
        UniqueConstraint(
            "api_key_hash",
            "idempotency_key_hash",
            name="uq_agnxiv_jobs_api_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    repository: Mapped[str] = mapped_column(String(255))
    repository_ref: Mapped[str] = mapped_column(String(255))
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    spec_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TransparencyHead(Base):
    __tablename__ = "agnxiv_transparency_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    head_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=GENESIS_HASH,
    )


class TransparencyEntry(Base):
    __tablename__ = "agnxiv_transparency_entries"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(32))
    repository: Mapped[str] = mapped_column(String(255))
    repository_ref: Mapped[str] = mapped_column(String(255))
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_sha256: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[str] = mapped_column(String(40))


class JobStore:
    def __init__(self, database_url: str) -> None:
        normalized_url = (
            "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
            if database_url.startswith("postgresql://")
            else database_url
        )
        self.database_url = normalized_url
        connect_args = (
            {"check_same_thread": False}
            if normalized_url.startswith("sqlite")
            else {}
        )
        self.engine = create_engine(
            normalized_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def initialize(self) -> None:
        if self.database_url.startswith("sqlite"):
            Base.metadata.create_all(self.engine)
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO agnxiv_transparency_head "
                        "(id, sequence, head_hash) VALUES (1, 0, :genesis)"
                    ),
                    {"genesis": GENESIS_HASH},
                )
                connection.execute(
                    text(
                        """
                        CREATE TRIGGER IF NOT EXISTS agnxiv_transparency_no_update
                        BEFORE UPDATE ON agnxiv_transparency_entries
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'agnxiv transparency ledger is append-only'
                            );
                        END
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        CREATE TRIGGER IF NOT EXISTS agnxiv_transparency_no_delete
                        BEFORE DELETE ON agnxiv_transparency_entries
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'agnxiv transparency ledger is append-only'
                            );
                        END
                        """
                    )
                )

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def create_job(
        self,
        *,
        job_id: str,
        api_key_hash: str,
        mode: str,
        repository: str,
        repository_ref: str,
        arxiv_id: str | None,
        spec_path: str | None,
        idempotency_key_hash: str | None = None,
        request_fingerprint: str | None = None,
    ) -> Job:
        job = Job(
            id=job_id,
            api_key_hash=api_key_hash,
            status="queued",
            mode=mode,
            repository=repository,
            repository_ref=repository_ref,
            arxiv_id=arxiv_id,
            spec_path=spec_path,
            idempotency_key_hash=idempotency_key_hash,
            request_fingerprint=request_fingerprint,
        )
        with self.session_factory() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def create_job_idempotent(
        self,
        *,
        job_id: str,
        api_key_hash: str,
        mode: str,
        repository: str,
        repository_ref: str,
        arxiv_id: str | None,
        spec_path: str | None,
        idempotency_key_hash: str,
        request_fingerprint: str,
    ) -> tuple[Job, bool]:
        """Create exactly one job for an API-key/idempotency-key pair."""
        job = Job(
            id=job_id,
            api_key_hash=api_key_hash,
            status="queued",
            mode=mode,
            repository=repository,
            repository_ref=repository_ref,
            arxiv_id=arxiv_id,
            spec_path=spec_path,
            idempotency_key_hash=idempotency_key_hash,
            request_fingerprint=request_fingerprint,
        )
        with self.session_factory() as session:
            session.add(job)
            try:
                session.commit()
                session.refresh(job)
                return job, True
            except IntegrityError:
                session.rollback()
                statement = select(Job).where(
                    Job.api_key_hash == api_key_hash,
                    Job.idempotency_key_hash == idempotency_key_hash,
                )
                existing = session.scalar(statement)
                if existing is None:
                    raise
                return existing, False

    def get_job(self, job_id: str) -> Job | None:
        with self.session_factory() as session:
            return session.get(Job, job_id)

    def get_by_idempotency(
        self,
        *,
        api_key_hash: str,
        idempotency_key_hash: str,
    ) -> Job | None:
        with self.session_factory() as session:
            statement = select(Job).where(
                Job.api_key_hash == api_key_hash,
                Job.idempotency_key_hash == idempotency_key_hash,
            )
            return session.scalar(statement)

    def metrics(self) -> dict[str, object]:
        """Return secret-free operator counters for the hosted control plane."""
        with self.session_factory() as session:
            status_rows = session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            ).all()
            mode_rows = session.execute(
                select(Job.mode, func.count()).group_by(Job.mode)
            ).all()
            total = int(session.scalar(select(func.count()).select_from(Job)) or 0)
            recent_cutoff = datetime.now(UTC) - timedelta(hours=1)
            recent = int(
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.created_at >= recent_cutoff)
                )
                or 0
            )
        statuses = {str(key): int(value) for key, value in status_rows}
        modes = {str(key): int(value) for key, value in mode_rows}
        return {
            "jobs_total": total,
            "jobs_last_hour": recent,
            "jobs_by_status": statuses,
            "jobs_by_mode": modes,
            "jobs_active": statuses.get("queued", 0) + statuses.get("running", 0),
        }

    def count_active(self, api_key_hash: str) -> int:
        with self.session_factory() as session:
            statement = select(func.count()).select_from(Job).where(
                Job.api_key_hash == api_key_hash,
                Job.status.in_(("queued", "running")),
            )
            return int(session.scalar(statement) or 0)

    def count_recent(self, api_key_hash: str, *, minutes: int = 60) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
        with self.session_factory() as session:
            statement = select(func.count()).select_from(Job).where(
                Job.api_key_hash == api_key_hash,
                Job.created_at >= cutoff,
            )
            return int(session.scalar(statement) or 0)

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status="running", error=None)

    def reap_stale(self, *, minutes: int) -> int:
        """Fail queued/running jobs whose callback never arrived."""
        cutoff = datetime.now(UTC) - timedelta(minutes=max(1, minutes))
        now = datetime.now(UTC)
        with self.session_factory() as session:
            statement = (
                update(Job)
                .where(
                    Job.status.in_(("queued", "running")),
                    Job.updated_at < cutoff,
                )
                .values(
                    status="failed",
                    error="hosted verification exceeded its callback deadline",
                    updated_at=now,
                )
            )
            result = session.execute(statement)
            session.commit()
            return int(result.rowcount or 0)

    def complete(
        self,
        job_id: str,
        *,
        status: str,
        result: dict | None,
        error: str | None,
    ) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.status = status
            job.result_json = (
                json.dumps(result, separators=(",", ":"))
                if result is not None
                else None
            )
            job.error = error
            job.updated_at = datetime.now(UTC)
            if result is not None and result.get("kind") == "verification":
                self._append_transparency_entry(
                    session,
                    job=job,
                    status=status,
                    result=result,
                )
            session.commit()

    def _append_transparency_entry(
        self,
        session,
        *,
        job: Job,
        status: str,
        result: dict,
    ) -> TransparencyEntry:
        # SQLite has no SELECT ... FOR UPDATE; a harmless write obtains its
        # database write lock before the head is read.
        if self.database_url.startswith("sqlite"):
            session.execute(
                text(
                    "UPDATE agnxiv_transparency_head "
                    "SET sequence = sequence WHERE id = 1"
                )
            )

        statement = select(TransparencyHead).where(TransparencyHead.id == 1)
        if not self.database_url.startswith("sqlite"):
            statement = statement.with_for_update()
        head = session.scalar(statement)
        if head is None:
            raise RuntimeError("transparency ledger head is not initialized")

        sequence = head.sequence + 1
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result_sha256 = digest_json(result)
        entry_hash = compute_entry_hash(
            sequence=sequence,
            job_id=job.id,
            status=status,
            mode=job.mode,
            repository=job.repository,
            repository_ref=job.repository_ref,
            arxiv_id=job.arxiv_id,
            result_sha256=result_sha256,
            previous_hash=head.head_hash,
            created_at=created_at,
        )
        entry = TransparencyEntry(
            sequence=sequence,
            job_id=job.id,
            status=status,
            mode=job.mode,
            repository=job.repository,
            repository_ref=job.repository_ref,
            arxiv_id=job.arxiv_id,
            result_sha256=result_sha256,
            previous_hash=head.head_hash,
            entry_hash=entry_hash,
            created_at=created_at,
        )
        session.add(entry)
        head.sequence = sequence
        head.head_hash = entry_hash
        return entry

    def transparency_head(self) -> tuple[int, str]:
        with self.session_factory() as session:
            head = session.get(TransparencyHead, 1)
            if head is None:
                raise RuntimeError("transparency ledger head is not initialized")
            return head.sequence, head.head_hash

    def get_transparency_entry(self, sequence: int) -> TransparencyEntry | None:
        with self.session_factory() as session:
            return session.get(TransparencyEntry, sequence)

    def list_transparency_entries(
        self,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[TransparencyEntry]:
        with self.session_factory() as session:
            statement = (
                select(TransparencyEntry)
                .where(TransparencyEntry.sequence > after_sequence)
                .order_by(TransparencyEntry.sequence)
                .limit(max(1, min(limit, 1000)))
            )
            return list(session.scalars(statement))

    def verify_transparency_chain(self) -> bool:
        previous_hash = GENESIS_HASH
        expected_sequence = 1
        for entry in self.list_transparency_entries(limit=1000):
            if entry.sequence != expected_sequence:
                return False
            if entry.previous_hash != previous_hash:
                return False
            expected_hash = compute_entry_hash(
                sequence=entry.sequence,
                job_id=entry.job_id,
                status=entry.status,
                mode=entry.mode,
                repository=entry.repository,
                repository_ref=entry.repository_ref,
                arxiv_id=entry.arxiv_id,
                result_sha256=entry.result_sha256,
                previous_hash=entry.previous_hash,
                created_at=entry.created_at,
            )
            if entry.entry_hash != expected_hash:
                return False
            previous_hash = entry.entry_hash
            expected_sequence += 1
        head_sequence, head_hash = self.transparency_head()
        return (
            head_sequence == expected_sequence - 1
            and head_hash == previous_hash
        )

    def _update(self, job_id: str, **values: object) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            for key, value in values.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(UTC)
            session.commit()


def job_result(job: Job) -> dict | None:
    if not job.result_json:
        return None
    return json.loads(job.result_json)
