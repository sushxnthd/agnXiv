from __future__ import annotations

import base64
from dataclasses import replace

from fastapi.testclient import TestClient

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.dispatcher import GitHubActionsDispatcher
from agnxiv.service.oidc import OIDCVerificationError
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
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=None,
    )


def test_hosted_job_lifecycle_oidc_and_quota(tmp_path, monkeypatch) -> None:
    dispatched = []

    def fake_dispatch(self, request):
        dispatched.append(request)
        return 12345

    monkeypatch.setattr(GitHubActionsDispatcher, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    monkeypatch.setattr(
        "agnxiv.service.app.verify_github_actions_token",
        lambda token, policy: {
            "repository": policy.repository,
            "ref": "refs/heads/main",
            "workflow_ref": (
                "sushxnthd/agnXiv/.github/workflows/hosted-verify.yml@refs/heads/main"
            ),
            "run_id": "12345",
        },
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
        assert created["repository_ref"] == "a" * 40
        assert len(dispatched) == 1
        assert dispatched[0].repository == "phanein/deepwalk"
        assert dispatched[0].arxiv_id == "1403.6652"
        assert dispatched[0].repository_ref == "a" * 40

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
            headers={"Authorization": "Bearer trusted-github-oidc"},
            json={
                "status": "needs_review",
                "result": {
                    "kind": "auto_plan",
                    "repository_commit": "a" * 40,
                    "plan": {
                        "automation_score": 0.75,
                        "safe_to_execute": False,
                    },
                },
            },
        )
        assert callback.status_code == 200

        replay = client.post(
            f"/internal/jobs/{created['id']}/complete",
            headers={"Authorization": "Bearer trusted-github-oidc"},
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


def test_hosted_callback_rejects_untrusted_oidc(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: 12345,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "b" * 40,
    )

    def reject(token, policy):
        raise OIDCVerificationError("wrong workflow")

    monkeypatch.setattr(
        "agnxiv.service.app.verify_github_actions_token",
        reject,
    )

    app = create_app(_config(f"sqlite:///{tmp_path / 'service.db'}"))

    with TestClient(app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "arxiv_id": "1403.6652",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        callback = client.post(
            f"/internal/jobs/{job_id}/complete",
            headers={"Authorization": "Bearer impostor"},
            json={"status": "failed", "error": "nope"},
        )
        assert callback.status_code == 401


def test_hosted_api_rejects_unsafe_inputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: 12345,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "c" * 40,
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
        max_jobs_per_hour=20,
        oidc_audience="http://localhost:8000/github-actions",
        issuer_private_key_b64=None,
    )
    app = create_app(config)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503


def test_issuer_endpoint_exposes_public_key(tmp_path) -> None:
    private_key, public_key, key_id = generate_ed25519_keypair()
    original = _config(f"sqlite:///{tmp_path / 'service.db'}")
    config = ServiceConfig(
        database_url=original.database_url,
        api_keys=original.api_keys,
        public_base_url=original.public_base_url,
        github_token=original.github_token,
        github_repository=original.github_repository,
        github_ref=original.github_ref,
        github_workflow=original.github_workflow,
        max_active_jobs_per_key=original.max_active_jobs_per_key,
        max_jobs_per_hour=original.max_jobs_per_hour,
        oidc_audience=original.oidc_audience,
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


def test_hosted_callback_rejects_wrong_pinned_commit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: 12345,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "d" * 40,
    )
    monkeypatch.setattr(
        "agnxiv.service.app.verify_github_actions_token",
        lambda token, policy: {"repository": policy.repository, "run_id": "12345"},
    )
    app = create_app(_config(f"sqlite:///{tmp_path / 'service.db'}"))

    with TestClient(app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "arxiv_id": "1403.6652",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        callback = client.post(
            f"/internal/jobs/{job_id}/complete",
            headers={"Authorization": "Bearer trusted"},
            json={
                "status": "needs_review",
                "result": {
                    "kind": "auto_plan",
                    "repository_commit": "e" * 40,
                    "plan": {
                        "automation_score": 0.75,
                        "safe_to_execute": False,
                    },
                },
            },
        )
        assert callback.status_code == 422

        fetched = client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "failed"


def test_hourly_quota_counts_finished_jobs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: 12345,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "f" * 40,
    )
    monkeypatch.setattr(
        "agnxiv.service.app.verify_github_actions_token",
        lambda token, policy: {"repository": policy.repository, "run_id": "12345"},
    )
    config = replace(
        _config(f"sqlite:///{tmp_path / 'service.db'}"),
        max_active_jobs_per_key=5,
        max_jobs_per_hour=1,
    )
    app = create_app(config)

    with TestClient(app) as client:
        first = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "arxiv_id": "1403.6652",
            },
        )
        assert first.status_code == 202

        completed = client.post(
            f"/internal/jobs/{first.json()['id']}/complete",
            headers={"Authorization": "Bearer trusted"},
            json={
                "status": "failed",
                "error": "controlled benchmark failure",
            },
        )
        assert completed.status_code == 200

        second = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "arxiv_id": "1403.6652",
            },
        )
        assert second.status_code == 429
        assert second.json()["detail"] == "hourly job quota exceeded"


def test_hosted_api_rejects_invalid_arxiv_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: 12345,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    app = create_app(_config(f"sqlite:///{tmp_path / 'service.db'}"))

    with TestClient(app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_plan",
                "repository": "phanein/deepwalk",
                "arxiv_id": "not-an-arxiv-paper",
            },
        )
        assert response.status_code == 422


def test_auto_verify_api_dispatches_and_rejects_fake_plan_success(
    tmp_path, monkeypatch,
) -> None:
    sent = []
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "dispatch",
        lambda self, request: (sent.append(request) or 12345),
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    monkeypatch.setattr(
        "agnxiv.service.app.verify_github_actions_token",
        lambda token, policy: {"repository": policy.repository, "run_id": "12345"},
    )
    app = create_app(_config(f"sqlite:///{tmp_path / 'service.db'}"))
    with TestClient(app) as client:
        missing = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={"mode": "auto_verify", "repository": "owner/repo"},
        )
        assert missing.status_code == 422

        created = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            json={
                "mode": "auto_verify",
                "repository": "phanein/deepwalk",
                "arxiv_id": "1403.6652",
            },
        )
        assert created.status_code == 202
        assert sent[0].mode == "auto_verify"
        assert sent[0].repository_ref == "a" * 40

        invalid = client.post(
            f"/internal/jobs/{created.json()['id']}/complete",
            headers={"Authorization": "Bearer trusted"},
            json={
                "status": "succeeded",
                "result": {
                    "kind": "auto_plan",
                    "repository_commit": "a" * 40,
                    "plan": {"safe_to_execute": True},
                },
            },
        )
        assert invalid.status_code == 422
