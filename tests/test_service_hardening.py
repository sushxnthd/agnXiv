from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.db import Job, JobStore


def _productionish_config(database_url: str, *, issuer: str | None = None) -> ServiceConfig:
    return ServiceConfig(
        database_url=database_url,
        api_keys=("k" * 48,),
        public_base_url="https://agnxiv.example",
        github_token="github-token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=issuer,
    )


def test_production_readiness_rejects_short_api_keys() -> None:
    config = ServiceConfig(
        database_url="postgresql://user:pass@example/db",
        api_keys=("short",),
        public_base_url="https://agnxiv.example",
        github_token="token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64="configured",
    )

    assert "api_key_too_short" in config.production_issues
    assert config.production_ready is False


def test_readiness_rejects_invalid_signing_key_without_exposing_secret(tmp_path) -> None:
    invalid = base64.b64encode(b"not-an-ed25519-private-key").decode("ascii")
    app = create_app(
        _productionish_config(
            f"sqlite:///{tmp_path / 'service.db'}",
            issuer=invalid,
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "issuer_key_invalid" in detail["issues"]
    assert invalid not in response.text


def test_meta_endpoint_exposes_capabilities_not_secrets(tmp_path) -> None:
    app = create_app(
        _productionish_config(
            f"sqlite:///{tmp_path / 'service.db'}",
            issuer=None,
        )
    )

    with TestClient(app) as client:
        response = client.get("/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["zero_manifest"] is True
    assert "auto_verify" in body["verification_modes"]
    assert body["signed_statements"] is False
    assert "github-token" not in response.text


def test_stale_jobs_are_failed_and_release_active_quota(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    store.initialize()
    job = store.create_job(
        job_id="00000000-0000-0000-0000-000000000001",
        api_key_hash="hash",
        mode="auto_verify",
        repository="owner/repo",
        repository_ref="a" * 40,
        arxiv_id="2601.00001",
        spec_path=None,
    )
    store.mark_running(job.id)

    with store.session_factory() as session:
        stored = session.get(Job, job.id)
        assert stored is not None
        stored.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        session.commit()

    assert store.count_active("hash") == 1
    assert store.reap_stale(minutes=5) == 1
    assert store.count_active("hash") == 0
    stale = store.get_job(job.id)
    assert stale is not None
    assert stale.status == "failed"
    assert "callback deadline" in (stale.error or "")
