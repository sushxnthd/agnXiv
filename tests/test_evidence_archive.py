from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
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


def test_evidence_commitment_is_public_but_capsule_requires_owner_key(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-archive.db'}"
    store = JobStore(database_url)
    store.initialize()
    publication = {
        "schema_version": "agnxiv.publication/1",
        "registry": "crossref",
        "doi": "10.1145/1234.5678",
        "publisher": "Example Publisher",
        "retrieved_at": "2026-10-19T00:00:00Z",
        "registry_record_sha256": "c" * 64,
    }
    job = store.create_job(
        job_id="00000000-0000-0000-0000-000000000779",
        api_key_hash="owner-hash",
        mode="auto_verify",
        repository="owner/repo",
        repository_ref="c" * 40,
        arxiv_id="2601.00079",
        doi="10.1145/1234.5678",
        publication=publication,
        spec_path=None,
    )
    store.complete(job.id, status="succeeded", result=_result(), error=None)

    config = ServiceConfig(
        database_url=database_url,
        api_keys=("owner-key",),
        public_base_url="https://agnxiv.example",
        github_token="token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=None,
    )
    app = create_app(config)
    with TestClient(app) as client:
        commitment = client.get(f"/v1/evidence/{job.id}/commitment")
        denied = client.get(f"/v1/jobs/{job.id}/evidence")

    assert commitment.status_code == 200
    assert commitment.json()["publication"]["doi"] == "10.1145/1234.5678"
    assert commitment.json()["source"]["repository_ref"] == "c" * 40
    assert denied.status_code == 401
