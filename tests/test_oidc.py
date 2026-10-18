import pytest

from agnxiv.service.oidc import (
    GitHubOIDCPolicy,
    OIDCVerificationError,
    verify_github_actions_token,
)


class _SigningKey:
    key = object()


def _policy() -> GitHubOIDCPolicy:
    return GitHubOIDCPolicy(
        audience="https://agnxiv.example/github-actions",
        repository="sushxnthd/agnXiv",
        ref="main",
        workflow="hosted-verify.yml",
    )


def _claims() -> dict:
    return {
        "repository": "sushxnthd/agnXiv",
        "ref": "refs/heads/main",
        "event_name": "workflow_dispatch",
        "workflow_ref": (
            "sushxnthd/agnXiv/.github/workflows/hosted-verify.yml@refs/heads/main"
        ),
        "runner_environment": "github-hosted",
    }


def test_oidc_policy_accepts_only_expected_workflow(monkeypatch) -> None:
    monkeypatch.setattr(
        "agnxiv.service.oidc._JWK_CLIENT.get_signing_key_from_jwt",
        lambda token: _SigningKey(),
    )
    monkeypatch.setattr(
        "agnxiv.service.oidc.jwt.decode",
        lambda *args, **kwargs: _claims(),
    )

    verified = verify_github_actions_token("token", _policy())

    assert verified["repository"] == "sushxnthd/agnXiv"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "attacker/repo"),
        ("ref", "refs/heads/evil"),
        ("event_name", "pull_request"),
        (
            "workflow_ref",
            "sushxnthd/agnXiv/.github/workflows/other.yml@refs/heads/main",
        ),
        ("runner_environment", "self-hosted"),
    ],
)
def test_oidc_policy_rejects_wrong_claim(
    field: str,
    value: str,
    monkeypatch,
) -> None:
    claims = _claims()
    claims[field] = value

    monkeypatch.setattr(
        "agnxiv.service.oidc._JWK_CLIENT.get_signing_key_from_jwt",
        lambda token: _SigningKey(),
    )
    monkeypatch.setattr(
        "agnxiv.service.oidc.jwt.decode",
        lambda *args, **kwargs: claims,
    )

    with pytest.raises(OIDCVerificationError, match=field):
        verify_github_actions_token("token", _policy())
