from __future__ import annotations

import re
from datetime import datetime

from .authority import (
    RegistryCheckpointQuorumPolicy,
    SignedRegistryCheckpoint,
    TrustedAuthorityRegistry,
    TrustedRegistryCheckpoint,
    TrustedRegistryCheckpointKey,
    authority_registry_blockers,
)
from .build import BuildResult
from .models import Verdict
from .pipeline import VerificationBundle
from .sandbox import is_immutable_image_id

_DECISIVE_VERDICTS = {
    Verdict.VERIFIED,
    Verdict.PARTIALLY_VERIFIED,
    Verdict.CONTRADICTED,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def environment_verdict_blockers(
    bundle: VerificationBundle,
    build: BuildResult,
    *,
    trusted_authority_registry: TrustedAuthorityRegistry | None = None,
    require_registry_authority: bool = False,
    authority_validation_time: datetime | None = None,
    trusted_minimum_registry_epoch: int | None = None,
    require_registry_freshness: bool = False,
    trusted_registry_checkpoint: TrustedRegistryCheckpoint | None = None,
    require_registry_checkpoint_scope: bool = False,
    signed_registry_checkpoint: SignedRegistryCheckpoint | None = None,
    signed_registry_checkpoints: list[SignedRegistryCheckpoint] | None = None,
    trusted_registry_checkpoint_keys: list[TrustedRegistryCheckpointKey] | None = None,
    require_authenticated_registry_checkpoint: bool = False,
    registry_checkpoint_quorum: RegistryCheckpointQuorumPolicy | None = None,
    require_registry_checkpoint_quorum: bool = False,
) -> list[str]:
    """Return independently inspectable reasons a hosted verdict must abstain."""
    blockers: list[str] = []
    environment = bundle.environment

    if bundle.verification_authority == "repository_supplied":
        blockers.append(
            "verification manifest and executable are supplied by the same "
            "untrusted repository; no independent verification authority is bound"
        )
    elif bundle.verification_authority != "auto_planned":
        blockers.append(
            "verification authority is missing; absence of provenance cannot "
            "establish independent verification authority"
        )
    elif (
        bundle.authority_evidence_sha256 is None
        or _SHA256_RE.fullmatch(bundle.authority_evidence_sha256) is None
    ):
        blockers.append(
            "auto-planned verification authority is not bound to canonical "
            "frozen-locator evidence"
        )
    elif require_registry_authority:
        blockers.extend(
            authority_registry_blockers(
                bundle,
                trusted_authority_registry,
                now=authority_validation_time,
                trusted_minimum_registry_epoch=trusted_minimum_registry_epoch,
                require_registry_freshness=require_registry_freshness,
                trusted_registry_checkpoint=trusted_registry_checkpoint,
                require_registry_checkpoint_scope=require_registry_checkpoint_scope,
                signed_registry_checkpoint=signed_registry_checkpoint,
                signed_registry_checkpoints=signed_registry_checkpoints,
                trusted_registry_checkpoint_keys=trusted_registry_checkpoint_keys,
                require_authenticated_registry_checkpoint=(
                    require_authenticated_registry_checkpoint
                ),
                registry_checkpoint_quorum=registry_checkpoint_quorum,
                require_registry_checkpoint_quorum=require_registry_checkpoint_quorum,
            )
        )
    if environment.scope_resolution == "ambiguous":
        blockers.append("workflow-scoped dependency environment is ambiguous")
    if environment.historical_fidelity != "constrained":
        blockers.append(
            "historical dependency fidelity is "
            f"{environment.historical_fidelity}, not constrained"
        )
    if build.plan.dependency_precision != "hash-pinned":
        blockers.append(
            "built dependency manifest precision is "
            f"{build.plan.dependency_precision}, not hash-pinned"
        )
    if not is_immutable_image_id(build.base_image_id):
        blockers.append("base image lacks a canonical immutable SHA-256 image ID")
    if not is_immutable_image_id(build.image_id):
        blockers.append("built environment lacks a canonical immutable SHA-256 image ID")
    if bundle.execution is None:
        blockers.append("scientific verdict lacks recorded execution image identity")
    elif not is_immutable_image_id(bundle.execution.image_id):
        blockers.append("execution lacks a canonical immutable SHA-256 image ID")
    elif bundle.execution.image_id != build.image_id:
        blockers.append(
            "executed image does not match the audited built environment image ID"
        )

    return blockers


def gate_hosted_verdict(
    bundle: VerificationBundle,
    build: BuildResult,
    *,
    trusted_authority_registry: TrustedAuthorityRegistry | None = None,
    require_registry_authority: bool = False,
    authority_validation_time: datetime | None = None,
    trusted_minimum_registry_epoch: int | None = None,
    require_registry_freshness: bool = False,
    trusted_registry_checkpoint: TrustedRegistryCheckpoint | None = None,
    require_registry_checkpoint_scope: bool = False,
    signed_registry_checkpoint: SignedRegistryCheckpoint | None = None,
    signed_registry_checkpoints: list[SignedRegistryCheckpoint] | None = None,
    trusted_registry_checkpoint_keys: list[TrustedRegistryCheckpointKey] | None = None,
    require_authenticated_registry_checkpoint: bool = False,
    registry_checkpoint_quorum: RegistryCheckpointQuorumPolicy | None = None,
    require_registry_checkpoint_quorum: bool = False,
) -> VerificationBundle:
    """Fail closed when environment drift remains an alternative explanation.

    Numeric measurements and their raw decision remain available for audit, but
    the public scientific verdict is suppressed at the hosted publication
    boundary.
    """
    if bundle.record.verdict not in _DECISIVE_VERDICTS:
        return bundle

    blockers = environment_verdict_blockers(
        bundle,
        build,
        trusted_authority_registry=trusted_authority_registry,
        require_registry_authority=require_registry_authority,
        authority_validation_time=authority_validation_time,
        trusted_minimum_registry_epoch=trusted_minimum_registry_epoch,
        require_registry_freshness=require_registry_freshness,
        trusted_registry_checkpoint=trusted_registry_checkpoint,
        require_registry_checkpoint_scope=require_registry_checkpoint_scope,
        signed_registry_checkpoint=signed_registry_checkpoint,
        signed_registry_checkpoints=signed_registry_checkpoints,
        trusted_registry_checkpoint_keys=trusted_registry_checkpoint_keys,
        require_authenticated_registry_checkpoint=require_authenticated_registry_checkpoint,
        registry_checkpoint_quorum=registry_checkpoint_quorum,
        require_registry_checkpoint_quorum=require_registry_checkpoint_quorum,
    )
    if not blockers:
        return bundle

    gated = bundle.model_copy(deep=True)
    raw_verdict = gated.record.verdict
    gated.provisional_verdict = raw_verdict
    gated.verdict_gate_reasons = blockers
    gated.record.verdict = Verdict.UNABLE_TO_VERIFY
    gated.record.rationale = (
        f"Hosted environment-fidelity gate suppressed provisional "
        f"{raw_verdict.value}: " + "; ".join(blockers) + ". "
        + gated.record.rationale
    )
    return gated
