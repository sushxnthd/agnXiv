from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient


class OIDCVerificationError(ValueError):
    """A GitHub Actions identity token could not be trusted."""


@dataclass(frozen=True)
class GitHubOIDCPolicy:
    audience: str
    repository: str
    ref: str
    workflow: str


_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
_ISSUER = "https://token.actions.githubusercontent.com"
_JWK_CLIENT = PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=3600)


def verify_github_actions_token(
    token: str,
    policy: GitHubOIDCPolicy,
) -> dict:
    """Verify a GitHub-hosted workflow identity against a strict trust policy."""
    try:
        signing_key = _JWK_CLIENT.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=policy.audience,
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "nbf", "jti", "repository", "ref"]},
        )
    except Exception as exc:
        raise OIDCVerificationError(f"invalid GitHub OIDC token: {exc}") from exc

    expected_ref = (
        policy.ref if policy.ref.startswith("refs/") else f"refs/heads/{policy.ref}"
    )
    expected_workflow_ref = (
        f"{policy.repository}/.github/workflows/{policy.workflow}@{expected_ref}"
    )

    checks = {
        "repository": claims.get("repository") == policy.repository,
        "ref": claims.get("ref") == expected_ref,
        "event_name": claims.get("event_name") == "workflow_dispatch",
        "workflow_ref": claims.get("workflow_ref") == expected_workflow_ref,
        "runner_environment": claims.get("runner_environment") == "github-hosted",
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise OIDCVerificationError(
            "GitHub OIDC trust policy rejected claims: " + ", ".join(failed)
        )

    return claims
