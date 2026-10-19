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
    workflow_sha: str | None = None
    run_id: int | None = None
    run_attempt: int = 1


_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
_ISSUER = "https://token.actions.githubusercontent.com"
_JWK_CLIENT = PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=300)


def _cached_signing_key(kid: str):
    """Resolve a GitHub signing key without refreshing JWKS on attacker-chosen misses."""
    try:
        keys = _JWK_CLIENT.get_signing_keys(refresh=False)
    except Exception as exc:
        raise OIDCVerificationError(f"GitHub JWKS is unavailable: {exc}") from exc
    for key in keys:
        if key.key_id == kid:
            return key
    raise OIDCVerificationError("GitHub OIDC signing key is not in the cached JWKS set")


def verify_github_actions_token(
    token: str,
    policy: GitHubOIDCPolicy,
) -> dict:
    """Verify a GitHub-hosted workflow identity against a strict trust policy."""
    if len(token) > 16_384 or token.count(".") != 2:
        raise OIDCVerificationError("invalid GitHub OIDC token shape")
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise OIDCVerificationError("invalid GitHub OIDC token header") from exc
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise OIDCVerificationError("unsupported GitHub OIDC signing header")
    try:
        signing_key = _cached_signing_key(header["kid"])
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=policy.audience,
            issuer=_ISSUER,
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "jti",
                    "repository",
                    "ref",
                    "workflow_ref",
                    "workflow_sha",
                    "run_id",
                    "run_attempt",
                ]
            },
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
        "workflow_sha": (
            policy.workflow_sha is None
            or claims.get("workflow_sha") == policy.workflow_sha
        ),
        "run_id": (
            policy.run_id is None
            or str(claims.get("run_id")) == str(policy.run_id)
        ),
        "run_attempt": str(claims.get("run_attempt")) == str(policy.run_attempt),
        "runner_environment": claims.get("runner_environment") == "github-hosted",
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise OIDCVerificationError(
            "GitHub OIDC trust policy rejected claims: " + ", ".join(failed)
        )

    return claims
