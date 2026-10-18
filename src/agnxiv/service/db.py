from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256

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
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


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
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class TransparencyEntry(Base):
    __tablename__ = "agnxiv_transparency_entries"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


_ZERO_HASH = "0" * 64


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _transparency_hash(
    *,
    sequence: int,
    job_id: str,
    status: str,
    payload_sha256: str,
    previous_hash: str,
    created_at: datetime,
) -> str:
    return _canonical_digest(
        {
            "schema_version": "agnxiv.transparency/1",
            "sequence": sequence,
            "job_id": job_id,
            "event_type": "job_finalized",
            "status": status,
            "payload_sha256": payload_sha256,
            "previous_hash": previous_hash,
            "created_at": _utc_text(created_at),
        }
    )


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
            with self.session_factory() as session:
                if session.get(TransparencyHead, 1) is None:
                    session.add(
                        TransparencyHead(
                            id=1,
                            sequence=0,
                            entry_hash=_ZERO_HASH,
                            updated_at=datetime.now(UTC),
                        )
                    )
                    session.commit()

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
        """Return secret-free operator counters for SLO and incident monitoring."""
        now = datetime.now(UTC)
        recent_cutoff = now - timedelta(hours=1)
        with self.session_factory() as session:
            status_rows = session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            ).all()
            mode_rows = session.execute(
                select(Job.mode, func.count()).group_by(Job.mode)
            ).all()
            total = int(session.scalar(select(func.count()).select_from(Job)) or 0)
            recent = int(
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.created_at >= recent_cutoff)
                )
                or 0
            )
            recent_terminal_rows = session.execute(
                select(Job.status, func.count())
                .where(
                    Job.updated_at >= recent_cutoff,
                    Job.status.in_(("succeeded", "needs_review", "failed")),
                )
                .group_by(Job.status)
            ).all()
            stale_failures = int(
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.updated_at >= recent_cutoff,
                        Job.status == "failed",
                        Job.error == "hosted verification exceeded its callback deadline",
                    )
                )
                or 0
            )
            oldest_active = session.scalar(
                select(func.min(Job.updated_at)).where(
                    Job.status.in_(("queued", "running"))
                )
            )
            transparency_count = int(
                session.scalar(
                    select(func.count()).select_from(TransparencyEntry)
                )
                or 0
            )

        statuses = {str(key): int(value) for key, value in status_rows}
        modes = {str(key): int(value) for key, value in mode_rows}
        terminal = {str(key): int(value) for key, value in recent_terminal_rows}
        terminal_total = sum(terminal.values())
        oldest_active_age = None
        if oldest_active is not None:
            if oldest_active.tzinfo is None:
                oldest_active = oldest_active.replace(tzinfo=UTC)
            oldest_active_age = max(
                0.0,
                (now - oldest_active.astimezone(UTC)).total_seconds(),
            )
        return {
            "jobs_total": total,
            "jobs_last_hour": recent,
            "jobs_by_status": statuses,
            "jobs_by_mode": modes,
            "jobs_active": statuses.get("queued", 0) + statuses.get("running", 0),
            "terminal_jobs_last_hour": terminal_total,
            "terminal_by_status_last_hour": terminal,
            "stale_callback_failures_last_hour": stale_failures,
            "stale_callback_fraction_last_hour": (
                stale_failures / terminal_total if terminal_total else 0.0
            ),
            "oldest_active_age_seconds": oldest_active_age,
            "transparency_entries": transparency_count,
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
        """Fail stale jobs and append one tamper-evident finalization entry each."""
        cutoff = datetime.now(UTC) - timedelta(minutes=max(1, minutes))
        with self.session_factory() as session:
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(
                        Job.status.in_(("queued", "running")),
                        Job.updated_at < cutoff,
                    )
                    .order_by(Job.created_at, Job.id)
                    .with_for_update()
                )
            )
            for job in jobs:
                now = datetime.now(UTC)
                job.status = "failed"
                job.error = "hosted verification exceeded its callback deadline"
                job.result_json = None
                job.updated_at = now
                self._append_transparency(
                    session,
                    job=job,
                    status="failed",
                    result=None,
                    error=job.error,
                    created_at=now,
                )
            session.commit()
            return len(jobs)

    def complete(
        self,
        job_id: str,
        *,
        status: str,
        result: dict | None,
        error: str | None,
    ) -> None:
        """Finalize a job and atomically append its transparency receipt."""
        with self.session_factory() as session:
            job = session.scalar(
                select(Job).where(Job.id == job_id).with_for_update()
            )
            if job is None:
                raise KeyError(job_id)
            now = datetime.now(UTC)
            job.status = status
            job.result_json = (
                json.dumps(result, separators=(",", ":")) if result else None
            )
            job.error = error
            job.updated_at = now
            self._append_transparency(
                session,
                job=job,
                status=status,
                result=result,
                error=error,
                created_at=now,
            )
            session.commit()

    def _append_transparency(
        self,
        session,
        *,
        job: Job,
        status: str,
        result: dict | None,
        error: str | None,
        created_at: datetime,
    ) -> TransparencyEntry:
        existing = session.scalar(
            select(TransparencyEntry).where(TransparencyEntry.job_id == job.id)
        )
        if existing is not None:
            raise ValueError(f"job already has a transparency entry: {job.id}")

        head = session.scalar(
            select(TransparencyHead)
            .where(TransparencyHead.id == 1)
            .with_for_update()
        )
        if head is None:
            head = TransparencyHead(
                id=1,
                sequence=0,
                entry_hash=_ZERO_HASH,
                updated_at=created_at,
            )
            session.add(head)
            session.flush()

        sequence = head.sequence + 1
        payload_sha256 = _canonical_digest(
            {
                "job_id": job.id,
                "status": status,
                "result": result,
                "error": error,
            }
        )
        entry_hash = _transparency_hash(
            sequence=sequence,
            job_id=job.id,
            status=status,
            payload_sha256=payload_sha256,
            previous_hash=head.entry_hash,
            created_at=created_at,
        )
        entry = TransparencyEntry(
            sequence=sequence,
            job_id=job.id,
            event_type="job_finalized",
            status=status,
            payload_sha256=payload_sha256,
            previous_hash=head.entry_hash,
            entry_hash=entry_hash,
            created_at=created_at,
        )
        session.add(entry)
        head.sequence = sequence
        head.entry_hash = entry_hash
        head.updated_at = created_at
        return entry

    def transparency_head(self) -> dict[str, object]:
        with self.session_factory() as session:
            head = session.get(TransparencyHead, 1)
            if head is None:
                return {"sequence": 0, "entry_hash": _ZERO_HASH}
            return {
                "sequence": head.sequence,
                "entry_hash": head.entry_hash,
                "updated_at": _utc_text(head.updated_at),
            }

    def transparency_entries(
        self,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        size = min(max(1, limit), 500)
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(TransparencyEntry)
                    .where(TransparencyEntry.sequence > max(0, after))
                    .order_by(TransparencyEntry.sequence)
                    .limit(size)
                )
            )
        return [self._transparency_view(row) for row in rows]

    def transparency_for_job(self, job_id: str) -> dict[str, object] | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(TransparencyEntry).where(TransparencyEntry.job_id == job_id)
            )
            return None if row is None else self._transparency_view(row)

    def verify_transparency_head(self) -> dict[str, object]:
        """Perform an O(1) integrity check suitable for readiness probes."""
        with self.session_factory() as session:
            head = session.get(TransparencyHead, 1)
            latest = session.scalar(
                select(TransparencyEntry)
                .order_by(TransparencyEntry.sequence.desc())
                .limit(1)
            )

        if head is None:
            return {"valid": False, "reason": "missing_head"}
        if head.sequence == 0:
            return {
                "valid": head.entry_hash == _ZERO_HASH and latest is None,
                "reason": (
                    None
                    if head.entry_hash == _ZERO_HASH and latest is None
                    else "empty_head_mismatch"
                ),
                "head_sequence": 0,
                "head_hash": head.entry_hash,
            }
        if latest is None or latest.sequence != head.sequence:
            return {
                "valid": False,
                "reason": "head_sequence_mismatch",
                "head_sequence": head.sequence,
            }
        computed = _transparency_hash(
            sequence=latest.sequence,
            job_id=latest.job_id,
            status=latest.status,
            payload_sha256=latest.payload_sha256,
            previous_hash=latest.previous_hash,
            created_at=latest.created_at,
        )
        if computed != latest.entry_hash or latest.entry_hash != head.entry_hash:
            return {
                "valid": False,
                "reason": "head_hash_mismatch",
                "head_sequence": head.sequence,
            }
        return {
            "valid": True,
            "reason": None,
            "head_sequence": head.sequence,
            "head_hash": head.entry_hash,
        }

    def verify_transparency_chain(self) -> dict[str, object]:
        """Verify the complete local hash chain and its materialized head."""
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(TransparencyEntry).order_by(TransparencyEntry.sequence)
                )
            )
            head = session.get(TransparencyHead, 1)

        expected_previous = _ZERO_HASH
        expected_sequence = 0
        for row in rows:
            expected_sequence += 1
            if row.sequence != expected_sequence:
                return {
                    "valid": False,
                    "reason": "sequence_gap",
                    "sequence": row.sequence,
                }
            if row.previous_hash != expected_previous:
                return {
                    "valid": False,
                    "reason": "previous_hash_mismatch",
                    "sequence": row.sequence,
                }
            computed = _transparency_hash(
                sequence=row.sequence,
                job_id=row.job_id,
                status=row.status,
                payload_sha256=row.payload_sha256,
                previous_hash=row.previous_hash,
                created_at=row.created_at,
            )
            if computed != row.entry_hash:
                return {
                    "valid": False,
                    "reason": "entry_hash_mismatch",
                    "sequence": row.sequence,
                }
            expected_previous = row.entry_hash

        if head is None:
            return {
                "valid": not rows,
                "reason": None if not rows else "missing_head",
                "entries": len(rows),
            }
        if head.sequence != expected_sequence or head.entry_hash != expected_previous:
            return {
                "valid": False,
                "reason": "head_mismatch",
                "entries": len(rows),
            }
        return {
            "valid": True,
            "reason": None,
            "entries": len(rows),
            "head_sequence": head.sequence,
            "head_hash": head.entry_hash,
        }

    @staticmethod
    def _transparency_view(row: TransparencyEntry) -> dict[str, object]:
        return {
            "schema_version": "agnxiv.transparency/1",
            "sequence": row.sequence,
            "job_id": row.job_id,
            "event_type": row.event_type,
            "status": row.status,
            "payload_sha256": row.payload_sha256,
            "previous_hash": row.previous_hash,
            "entry_hash": row.entry_hash,
            "created_at": _utc_text(row.created_at),
        }

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
