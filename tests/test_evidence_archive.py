from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from agnxiv.service.db import JobStore


def _result() -> dict:
    return {
        "kind": "verification",
        "zero_manifest": True,
        "statement": {"predicateType": "https://agnxiv.org/attestation/verification/v1"},
        "dsseEnvelope": {"payloadType": "application/vnd.in-toto+json"},
        "bundle": {"record": {"verdict": "VERIFIED"}},
    }


def test_verification_creates_content_addressed_evidence_archive(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'archive.db'}")
    store.initialize()
    publication = {
        "schema_version": "agnxiv.publication/1",
        "registry": "crossref",
        "doi": "10.1145/1234.5678",
        "publisher": "Example Publisher",
        "retrieved_at": "2026-10-19T00:00:00Z",
        "registry_record_sha256": "a" * 64,
    }
    job = store.create_job(
        job_id="00000000-0000-0000-0000-000000000777",
        api_key_hash="hash",
        mode="auto_verify",
        repository="owner/repo",
        repository_ref="a" * 40,
        arxiv_id="2601.00077",
        doi="10.1145/1234.5678",
        publication=publication,
        spec_path=None,
    )
    store.complete(job.id, status="succeeded", result=_result(), error=None)

    archive = store.get_evidence_archive(job.id)
    assert archive is not None
    assert len(archive.content_sha256) == 64
    assert archive.retention_policy == "public-verification-10y-minimum"
    assert archive.transparency_sequence == 1
    assert store.verify_evidence_archive(job.id) is True

    payload = json.loads(archive.payload_json)
    assert payload["publication"]["doi"] == "10.1145/1234.5678"
    assert payload["job"]["repository_ref"] == "a" * 40
    assert payload["transparency"]["entry_hash"] == archive.transparency_entry_hash
    created = datetime.fromisoformat(archive.created_at)
    retained = datetime.fromisoformat(archive.retain_until)
    assert (retained - created).days >= 3650


def test_evidence_archive_rejects_update_and_delete(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'immutable.db'}")
    store.initialize()
    job = store.create_job(
        job_id="00000000-0000-0000-0000-000000000778",
        api_key_hash="hash",
        mode="auto_verify",
        repository="owner/repo",
        repository_ref="b" * 40,
        arxiv_id="2601.00078",
        spec_path=None,
    )
    store.complete(job.id, status="succeeded", result=_result(), error=None)

    for sql in (
        "UPDATE agnxiv_evidence_archives SET retention_policy='forged' WHERE job_id=:job",
        "DELETE FROM agnxiv_evidence_archives WHERE job_id=:job",
    ):
        with (
            pytest.raises(SQLAlchemyError, match="append-only"),
            store.engine.begin() as connection,
        ):
            connection.execute(text(sql), {"job": job.id})

    assert store.verify_evidence_archive(job.id) is True
