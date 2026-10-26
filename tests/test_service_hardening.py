from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agnxiv.attestation import canonical_json_sha256
from agnxiv.service.app import _validate_worker_result, create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.db import Job, JobStore
from agnxiv.service.dispatcher import GitHubActionsDispatcher


def _worker_bundle(
    authority: str | None,
    commit: str,
    *,
    discovery: dict | None = None,
) -> dict:
    claim = {"id": "C1", "text": "Accuracy is 0.9", "reported_value": 0.9}
    return {
        "verification_authority": authority,
        "authority_evidence_sha256": (
            canonical_json_sha256(discovery) if discovery is not None else None
        ),
        "claim": claim,
        "provenance": {
            "tree_digest": "a" * 64,
            "git": {"commit": commit, "dirty": False},
            "files": [],
            "file_count": 0,
            "total_bytes": 0,
        },
        "environment": {},
        "record": {
            "claim": claim,
            "policy": {"kind": "absolute", "tolerance": 0.01},
            "observations": [{"value": 0.9}],
            "verdict": "VERIFIED",
            "expected": 0.9,
            "observed_mean": 0.9,
            "absolute_error": 0.0,
            "relative_error": 0.0,
            "rationale": "matched",
        },
    }


def _worker_job(mode: str, commit: str) -> Job:
    return Job(
        id="00000000-0000-0000-0000-000000000099",
        api_key_hash="hash",
        status="running",
        mode=mode,
        repository="owner/repo",
        repository_ref=commit,
        arxiv_id="2601.00001",
        spec_path=None,
    )


def test_worker_authority_must_match_verification_mode() -> None:
    commit = "a" * 40
    discovery = {"claim_id": "C1", "metric": "accuracy", "regex": "x"}
    auto_result = {
        "kind": "verification",
        "zero_manifest": True,
        "discovery": discovery,
        "bundle": _worker_bundle("auto_planned", commit, discovery=discovery),
    }
    assert _validate_worker_result(
        _worker_job("auto_verify", commit), "succeeded", auto_result
    ) is not None

    auto_result["bundle"]["verification_authority"] = None
    try:
        _validate_worker_result(
            _worker_job("auto_verify", commit), "succeeded", auto_result
        )
    except ValueError as exc:
        assert "invalid verification authority" in str(exc)
    else:
        raise AssertionError("missing worker authority was accepted")

    spec_result = {
        "kind": "verification",
        "bundle": _worker_bundle("repository_supplied", commit),
    }
    assert _validate_worker_result(
        _worker_job("verify_spec", commit), "succeeded", spec_result
    ) is not None

    spec_result["bundle"]["verification_authority"] = "auto_planned"
    try:
        _validate_worker_result(
            _worker_job("verify_spec", commit), "succeeded", spec_result
        )
    except ValueError as exc:
        assert "invalid verification authority" in str(exc)
    else:
        raise AssertionError("repository worker claimed auto-planned authority")


def test_worker_rejects_cross_locator_authority_substitution() -> None:
    commit = "b" * 40
    locator_a = {"claim_id": "C1", "metric": "accuracy", "regex": "A"}
    locator_b = {"claim_id": "C2", "metric": "f1", "regex": "B"}
    result = {
        "kind": "verification",
        "zero_manifest": True,
        "discovery": locator_b,
        "bundle": _worker_bundle("auto_planned", commit, discovery=locator_a),
    }

    try:
        _validate_worker_result(
            _worker_job("auto_verify", commit), "succeeded", result
        )
    except ValueError as exc:
        assert "not bound to its frozen locator" in str(exc)
    else:
        raise AssertionError("cross-locator authority substitution was accepted")


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



def test_hosted_job_submission_is_idempotent(tmp_path, monkeypatch) -> None:
    dispatched = []
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: dispatched.append(request),
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    config = _productionish_config(
        f"sqlite:///{tmp_path / 'service.db'}",
        issuer=None,
    )
    app = create_app(config)
    headers = {
        "X-API-Key": "k" * 48,
        "Idempotency-Key": "verify-paper-2601-00001",
    }
    body = {
        "mode": "auto_verify",
        "repository": "owner/repo",
        "repository_ref": "main",
        "arxiv_id": "2601.00001",
    }

    with TestClient(app) as client:
        first = client.post("/v1/jobs", headers=headers, json=body)
        second = client.post("/v1/jobs", headers=headers, json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert len(dispatched) == 1


def test_idempotency_key_reuse_for_different_request_is_rejected(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: None,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "b" * 40,
    )
    app = create_app(
        _productionish_config(
            f"sqlite:///{tmp_path / 'service.db'}",
            issuer=None,
        )
    )
    headers = {
        "X-API-Key": "k" * 48,
        "Idempotency-Key": "same-key-different-input",
    }

    with TestClient(app) as client:
        first = client.post(
            "/v1/jobs",
            headers=headers,
            json={
                "mode": "auto_verify",
                "repository": "owner/repo",
                "arxiv_id": "2601.00001",
            },
        )
        second = client.post(
            "/v1/jobs",
            headers=headers,
            json={
                "mode": "auto_verify",
                "repository": "owner/repo",
                "arxiv_id": "2601.00002",
            },
        )

    assert first.status_code == 202
    assert second.status_code == 409


def test_store_idempotency_constraint_returns_existing_job(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'idempotent.db'}")
    store.initialize()
    kwargs = {
        "api_key_hash": "api-hash",
        "mode": "auto_verify",
        "repository": "owner/repo",
        "repository_ref": "c" * 40,
        "arxiv_id": "2601.00001",
        "spec_path": None,
        "idempotency_key_hash": "idem-hash",
        "request_fingerprint": "request-hash",
    }

    first, created_first = store.create_job_idempotent(
        job_id="00000000-0000-0000-0000-000000000011",
        **kwargs,
    )
    second, created_second = store.create_job_idempotent(
        job_id="00000000-0000-0000-0000-000000000012",
        **kwargs,
    )

    assert created_first is True
    assert created_second is False
    assert second.id == first.id



def test_metrics_endpoint_requires_auth_and_reports_job_counts(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: None,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "d" * 40,
    )
    app = create_app(
        _productionish_config(
            f"sqlite:///{tmp_path / 'metrics.db'}",
            issuer=None,
        )
    )

    with TestClient(app) as client:
        denied = client.get("/v1/metrics")
        assert denied.status_code == 401

        created = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "k" * 48},
            json={
                "mode": "auto_verify",
                "repository": "owner/repo",
                "arxiv_id": "2601.00001",
            },
        )
        assert created.status_code == 202

        metrics = client.get(
            "/v1/metrics",
            headers={"X-API-Key": "k" * 48},
        )

    assert metrics.status_code == 200
    body = metrics.json()
    assert body["schema_version"] == "agnxiv.metrics/1"
    assert body["jobs_total"] == 1
    assert body["jobs_active"] == 1
    assert body["jobs_by_mode"]["auto_verify"] == 1


def test_request_id_is_echoed_and_untrusted_values_are_replaced(tmp_path) -> None:
    app = create_app(
        _productionish_config(
            f"sqlite:///{tmp_path / 'request-id.db'}",
            issuer=None,
        )
    )

    with TestClient(app) as client:
        valid = client.get(
            "/healthz",
            headers={"X-Request-ID": "trace-123"},
        )
        invalid = client.get(
            "/healthz",
            headers={"X-Request-ID": "bad request id with spaces"},
        )

    assert valid.headers["X-Request-ID"] == "trace-123"
    assert invalid.headers["X-Request-ID"] != "bad request id with spaces"
    assert len(invalid.headers["X-Request-ID"]) == 32
