from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Mapping


class WorkerBoundaryError(RuntimeError):
    """The hosted worker is not inside the required outer isolation boundary."""


_SENSITIVE_ENV = (
    "AGNXIV_API_KEYS",
    "AGNXIV_GITHUB_TOKEN",
    "AGNXIV_ISSUER_PRIVATE_KEY_B64",
    "DATABASE_URL",
    "GITHUB_TOKEN",
)


@dataclass(frozen=True)
class WorkerBoundaryAttestation:
    provider: str
    runner_environment: str
    ephemeral_vm: bool
    oidc_available: bool
    sensitive_env_exposed: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def attest_worker_boundary(
    environ: Mapping[str, str] | None = None,
    *,
    strict: bool = False,
) -> WorkerBoundaryAttestation:
    env = dict(os.environ if environ is None else environ)
    github_actions = env.get("GITHUB_ACTIONS", "").lower() == "true"
    runner_environment = env.get("RUNNER_ENVIRONMENT", "")
    hosted_vm = github_actions and runner_environment == "github-hosted"
    oidc_available = bool(
        env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        or env.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    )
    sensitive = tuple(name for name in _SENSITIVE_ENV if env.get(name))

    attestation = WorkerBoundaryAttestation(
        provider="github-actions" if github_actions else "local",
        runner_environment=runner_environment or "unknown",
        ephemeral_vm=hosted_vm,
        oidc_available=oidc_available,
        sensitive_env_exposed=sensitive,
    )

    if strict:
        if not hosted_vm:
            raise WorkerBoundaryError(
                "hosted research execution requires a GitHub-hosted ephemeral VM"
            )
        if oidc_available:
            raise WorkerBoundaryError(
                "research execution job must not have OIDC token access"
            )
        if sensitive:
            raise WorkerBoundaryError(
                "research execution job exposes service credentials: "
                + ", ".join(sensitive)
            )

    return attestation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    print(json.dumps(attest_worker_boundary(strict=args.strict).as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
