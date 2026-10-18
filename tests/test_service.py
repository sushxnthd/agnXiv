from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi.testclient import TestClient

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.dispatcher import GitHubActionsDispatcher
from agnxiv.statement import generate_ed25519_keypair


def _config(database_url: str) -> ServiceConfig:
    return ServiceConfig(
        database_url=database_url,
        api_keys=("test-key",),
        public_base_url="https://agnxiv.example",
        github_token="test-token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=1,
        callback_secret="callback-secret",
        issuer_private_key_b64=None,
    )


def _callback_token(job_id: str) -> str:
    nonce = "fixed-nonce"
    signature = hmac.new(
        b"callback-secret",
        f"{job_id}.{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{nonce}.{signature}"


def test_hosted_job_lifecycle_and_quota(tmp_path, monkeypatch) -> None:
    dispatched = []

    def fake_dispatch(self, request):
        dispatched.append(request)

    monkeypatch.setattr(GitHubActionsDispatcher, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        "agnxiv.service.app.secrets.token_urlsafe",
        lambda _: "fixed-nonce",
    )

    database = f"sqlite:///{tmp_path / 'service.db'}"
    app = create_app(_config(database))

    with TestClient(app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "https://github.com/phanein/deepwalk",
                "repository_ref": "6e6dff245e4692e9bea47e9017c1034e51afbf29",
                "arxiv_id": "1403.6652",
            },
        )
        assert response.status_code == 202
        created = response.json()
        assert created["status"] == "running"
        assert created["repository"] == "phanein/deepwalk"
        assert len(dispatched) == 1
        assert dispatched[0].repository == "phanein/deepwalk"
        assert dispatched[0].arxiv_id == "1403.6652"

        quota = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "repository_ref": "main",
                "arxiv_id": "1403.6652",
            },
        )
        assert quota.status_code == 429

        wrong_key = client.get(
            f"/v1/jobs/{created['id']}",
            headers={"X-API-Key": "wrong"},
        )
        assert wrong_key.status_code == 401

        callback = client.post(
            f"/internal/jobs/{created['id']}/complete",
            headers={
                "X-AgnXiv-Callback-Token": _callback_token(created["id"]),
            },
            json={
                "status": "needs_review",
                "result": {
                    "kind": "auto_plan",
                    "plan": {"automation_score": 0.75},
                },
            },
        )
        assert callback.status_code == 200

        replay = client.post(
            f"/internal/jobs/{created['id']}/complete",
            headers={
                "X-AgnXiv-Callback-Token": _callback_token(created["id"]),
            },
            json={
                "status": "failed",
                "error": "attempted overwrite",
            },
        )
        assert replay.status_code == 409

        fetched = client.get(
            f"/v1/jobs/{created['id']}",
            headers={"X-API-Key": "test-key"},
        )
        assert fetched.status_code == 200
        final = fetched.json()
        assert final["status"] == "needs_review"
        assert final["result"]["plan"]["automation_score"] == 0.75


def test_hosted_api_rejects_unsafe_inputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: None,
    )
    app = create_app(_config(f"sqlite:///{tmp_path / 'service.db'}"))

    with TestClient(app) as client:
        bad_repo = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "https://evil.example/repo",
                "arxiv_id": "1403.6652",
            },
        )
        assert bad_repo.status_code == 422

        unsafe_spec = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "verify_spec",
                "repository": "owner/repo",
                "spec_path": "../secret.json",
            },
        )
        assert unsafe_spec.status_code == 422


def test_readiness_requires_production_configuration(tmp_path) -> None:
    config = ServiceConfig(
        database_url=f"sqlite:///{tmp_path / 'service.db'}",
        api_keys=(),
        public_base_url="http://localhost:8000",
        github_token=None,
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        callback_secret="development-only-change-me",
        issuer_private_key_b64=None,
    )
    app = create_app(config)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503


def test_issuer_endpoint_exposes_public_key(tmp_path) -> None:
    private_key, public_key, key_id = generate_ed25519_keypair()
    config = _config(f"sqlite:///{tmp_path / 'service.db'}")
    config = ServiceConfig(
        database_url=config.database_url,
        api_keys=config.api_keys,
        public_base_url=config.public_base_url,
        github_token=config.github_token,
        github_repository=config.github_repository,
        github_ref=config.github_ref,
        github_workflow=config.github_workflow,
        max_active_jobs_per_key=config.max_active_jobs_per_key,
        callback_secret=config.callback_secret,
        issuer_private_key_b64=base64.b64encode(private_key).decode("ascii"),
    )
    app = create_app(config)

    with TestClient(app) as client:
        response = client.get("/v1/issuer")
        assert response.status_code == 200
        issuer = response.json()
        assert issuer["algorithm"] == "Ed25519"
        assert issuer["key_id"] == key_id
        assert issuer["public_key_pem"].encode("ascii") == public_key
