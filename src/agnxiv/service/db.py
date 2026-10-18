from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "agnxiv_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    repository: Mapped[str] = mapped_column(String(255))
    repository_ref: Mapped[str] = mapped_column(String(255))
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    spec_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    callback_token_hash: Mapped[str] = mapped_column(String(64))
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


class JobStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_job(
        self,
        *,
        api_key_hash: str,
        mode: str,
        repository: str,
        repository_ref: str,
        arxiv_id: str | None,
        spec_path: str | None,
        callback_token_hash: str,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            api_key_hash=api_key_hash,
            status="queued",
            mode=mode,
            repository=repository,
            repository_ref=repository_ref,
            arxiv_id=arxiv_id,
            spec_path=spec_path,
            callback_token_hash=callback_token_hash,
        )
        with self.session_factory() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self.session_factory() as session:
            return session.get(Job, job_id)

    def count_active(self, api_key_hash: str) -> int:
        with self.session_factory() as session:
            statement = select(func.count()).select_from(Job).where(
                Job.api_key_hash == api_key_hash,
                Job.status.in_(("queued", "running")),
            )
            return int(session.scalar(statement) or 0)

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status="running", error=None)

    def complete(
        self,
        job_id: str,
        *,
        status: str,
        result: dict | None,
        error: str | None,
    ) -> None:
        self._update(
            job_id,
            status=status,
            result_json=json.dumps(result, separators=(",", ":")) if result else None,
            error=error,
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
