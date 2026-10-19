import pytest

from agnxiv.worker_boundary import WorkerBoundaryError, attest_worker_boundary


def test_github_hosted_execution_boundary_is_accepted() -> None:
    attestation = attest_worker_boundary(
        {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
        },
        strict=True,
    )
    assert attestation.ephemeral_vm is True
    assert attestation.provider == "github-actions"
    assert attestation.oidc_available is False
    assert attestation.sensitive_env_exposed == ()


def test_self_hosted_runner_is_rejected_in_strict_mode() -> None:
    with pytest.raises(WorkerBoundaryError, match="GitHub-hosted ephemeral VM"):
        attest_worker_boundary(
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "self-hosted",
            },
            strict=True,
        )


def test_oidc_and_service_credentials_are_rejected_from_execution_job() -> None:
    with pytest.raises(WorkerBoundaryError, match="OIDC token"):
        attest_worker_boundary(
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "present",
            },
            strict=True,
        )

    with pytest.raises(WorkerBoundaryError, match="service credentials"):
        attest_worker_boundary(
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "DATABASE_URL": "postgresql://secret",
            },
            strict=True,
        )
