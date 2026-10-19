from agnxiv.service.config import ServiceConfig
from agnxiv.service.dispatcher import GitHubActionsDispatcher
from agnxiv.service.preflight import evaluate_production_preflight


def _config() -> ServiceConfig:
    return ServiceConfig(
        database_url="postgresql://user:pass@example/db",
        api_keys=("k" * 48,),
        public_base_url="https://agnxiv.example",
        github_token="token",
        github_repository="sushxnthd/agnXiv",
        github_ref="refs/tags/agnxiv-release-test",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64="configured",
        github_workflow_sha="a" * 40,
    )


def test_production_preflight_accepts_matching_protected_release(monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "repository_release_posture",
        lambda self: {
            "default_branch": "main",
            "default_branch_protected": True,
        },
    )

    report = evaluate_production_preflight(_config())

    assert report["ready"] is True
    assert report["issues"] == []


def test_production_preflight_rejects_moved_release_ref(monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "b" * 40,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "repository_release_posture",
        lambda self: {
            "default_branch": "main",
            "default_branch_protected": True,
        },
    )

    report = evaluate_production_preflight(_config())

    assert report["ready"] is False
    assert "trusted_workflow_ref_sha_mismatch" in report["issues"]


def test_production_preflight_rejects_unprotected_default_branch(monkeypatch) -> None:
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "resolve_commit",
        lambda self, repository, ref: "a" * 40,
    )
    monkeypatch.setattr(
        GitHubActionsDispatcher,
        "repository_release_posture",
        lambda self: {
            "default_branch": "main",
            "default_branch_protected": False,
        },
    )

    report = evaluate_production_preflight(_config())

    assert report["ready"] is False
    assert "default_branch_unprotected" in report["issues"]
