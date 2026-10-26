from __future__ import annotations

from .build import BuildResult
from .models import Verdict
from .pipeline import VerificationBundle
from .sandbox import is_immutable_image_id

_DECISIVE_VERDICTS = {
    Verdict.VERIFIED,
    Verdict.PARTIALLY_VERIFIED,
    Verdict.CONTRADICTED,
}


def environment_verdict_blockers(
    bundle: VerificationBundle,
    build: BuildResult,
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
) -> VerificationBundle:
    """Fail closed when environment drift remains an alternative explanation.

    Numeric measurements and their raw decision remain available for audit, but
    the public scientific verdict is suppressed at the hosted publication
    boundary.
    """
    if bundle.record.verdict not in _DECISIVE_VERDICTS:
        return bundle

    blockers = environment_verdict_blockers(bundle, build)
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
