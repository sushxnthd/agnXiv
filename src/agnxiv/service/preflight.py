from __future__ import annotations

import json
from .config import ServiceConfig
from .dispatcher import DispatchError, GitHubActionsDispatcher


class ProductionPreflightError(RuntimeError):
    """Production deployment prerequisites are not satisfied."""


def evaluate_production_preflight(config: ServiceConfig) -> dict[str, object]:
    issues = list(config.production_issues)
    posture: dict[str, object] | None = None
    resolved_ref: str | None = None

    if config.github_token:
        dispatcher = GitHubActionsDispatcher(
            token=config.github_token,
            repository=config.github_repository,
            ref=config.github_ref,
            workflow=config.github_workflow,
        )
        try:
            resolved_ref = dispatcher.resolve_commit(
                config.github_repository,
                config.github_ref,
            )
            posture = dispatcher.repository_release_posture()
        except DispatchError as exc:
            issues.append("github_release_posture_unavailable")
            posture = {"error": type(exc).__name__}

    if (
        resolved_ref is not None
        and config.github_workflow_sha is not None
        and resolved_ref != config.github_workflow_sha
    ):
        issues.append("trusted_workflow_ref_sha_mismatch")

    if posture is not None and posture.get("default_branch_protected") is not True:
        issues.append("default_branch_unprotected")

    report = {
        "schema_version": "agnxiv.production-preflight/1",
        "ready": not issues,
        "issues": sorted(set(issues)),
        "github": {
            "repository": config.github_repository,
            "trusted_ref": config.github_ref,
            "trusted_workflow": config.github_workflow,
            "configured_workflow_sha": config.github_workflow_sha,
            "resolved_ref_sha": resolved_ref,
            "release_posture": posture,
        },
        "config": {
            "database": config.database_url.split(":", 1)[0],
            "public_base_url": config.public_base_url,
            "development_auth_enabled": config.allow_development_auth,
            "api_key_count": len(config.api_keys),
            "previous_issuer_keys": len(config.issuer_previous_public_keys_b64),
        },
    }
    return report


def main() -> None:
    config = ServiceConfig.from_env()
    report = evaluate_production_preflight(config)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
