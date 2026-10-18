import pytest

from agnxiv.service.oidc import (
    GitHubOIDCPolicy,
    OIDCVerificationError,
    verify_github_actions_token,
)


class _SigningKey:
    key = object()


_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImsifQ.e30.c2ln"


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

    verified = verify_github_actions_token(_TOKEN, _policy())

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
        verify_github_actions_token(_TOKEN, _policy())


def test_oidc_rejects_malformed_token_before_jwks_lookup(monkeypatch) -> None:
    called = False

    def should_not_run(token):
        nonlocal called
        called = True
        raise AssertionError("JWKS lookup should not run")

    monkeypatch.setattr(
        "agnxiv.service.oidc._JWK_CLIENT.get_signing_key_from_jwt",
        should_not_run,
    )

    with pytest.raises(OIDCVerificationError, match="token shape"):
        verify_github_actions_token("not-a-jwt", _policy())
    with pytest.raises(OIDCVerificationError, match="token shape"):
        verify_github_actions_token("a" * 20_000, _policy())
    assert called is False


def test_oidc_rejects_wrong_algorithm_before_jwks_lookup(monkeypatch) -> None:
    called = False

    def should_not_run(token):
        nonlocal called
        called = True
        raise AssertionError("JWKS lookup should not run")

    monkeypatch.setattr(
        "agnxiv.service.oidc._JWK_CLIENT.get_signing_key_from_jwt",
        should_not_run,
    )
    hs_token = "eyJhbGciOiJIUzI1NiIsImtpZCI6ImsifQ.e30.c2ln"
    with pytest.raises(OIDCVerificationError, match="signing header"):
        verify_github_actions_token(hs_token, _policy())
    assert called is False
