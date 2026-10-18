from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field

from .environment import EnvironmentSpec, infer_python_environment
from .evidence import EvidenceCandidate, map_claim_to_repository
from .models import (
    Claim,
    Observation,
    Verdict,
    VerificationPolicy,
    VerificationRecord,
)
from .outputs import (
    ObservationCandidate,
    extract_json_observation,
    extract_observation_candidates,
    select_unambiguous_observation,
)
from .planner import CommandCandidate, discover_commands
from .provenance import (
    DocumentFingerprint,
    ProvenanceManifest,
    fingerprint_document,
    fingerprint_tree,
)
from .sandbox import ExecutionResult, SandboxError, SandboxLimits, execute_in_docker
from .verify import verify_numeric_claim


class ExecutionSummary(BaseModel):
    command: list[str]
    image_id: str
    returncode: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_excerpt: str
    stderr_excerpt: str
    pre_execution_tree_sha256: str
    post_execution_tree_sha256: str
    source_unchanged: bool


class VerificationBundle(BaseModel):
    schema_version: str = "agnxiv.bundle/0.4"
    claim: Claim
    manuscript: DocumentFingerprint | None = None
    provenance: ProvenanceManifest
    environment: EnvironmentSpec
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    command_candidates: list[CommandCandidate] = Field(default_factory=list)
    execution: ExecutionSummary | None = None
    observation_method: str | None = None
    observation_locator: str | None = None
    observation_candidates: list[ObservationCandidate] = Field(default_factory=list)
    record: VerificationRecord


def _unable_record(
    claim: Claim,
    policy: VerificationPolicy,
    *,
    rationale: str,
    observations: list[Observation] | None = None,
) -> VerificationRecord:
    values = observations or []
    return VerificationRecord(
        claim=claim,
        policy=policy,
        observations=values,
        verdict=Verdict.UNABLE_TO_VERIFY,
        expected=claim.reported_value,
        observed_mean=None,
        absolute_error=None,
        relative_error=None,
        rationale=rationale,
    )


def inspect_project(
    claim: Claim,
    repository: str | Path,
) -> tuple[
    ProvenanceManifest,
    EnvironmentSpec,
    list[EvidenceCandidate],
    list[CommandCandidate],
]:
    """Perform all non-executing inspection stages for a claim."""
    return (
        fingerprint_tree(repository),
        infer_python_environment(repository),
        map_claim_to_repository(claim, repository),
        discover_commands(repository),
    )


def verify_with_command(
    claim: Claim,
    repository: str | Path,
    *,
    image: str,
    command: list[str],
    policy: VerificationPolicy,
    manuscript_path: str | Path | None = None,
    json_path: str | None = None,
    observation_scale: float = 1.0,
    limits: SandboxLimits | None = None,
) -> VerificationBundle:
    """Execute one explicit research command and verify one numeric claim."""
    active_limits = limits or SandboxLimits()
    provenance, environment, evidence, commands = inspect_project(claim, repository)
    manuscript = (
        fingerprint_document(manuscript_path) if manuscript_path is not None else None
    )

    try:
        result: ExecutionResult = execute_in_docker(
            image=image,
            repository=repository,
            command=command,
            limits=active_limits,
        )
    except SandboxError as exc:
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            environment=environment,
            evidence_candidates=evidence,
            command_candidates=commands,
            record=_unable_record(
                claim,
                policy,
                rationale=f"Execution could not be completed: {exc}",
            ),
        )

    post_provenance = fingerprint_tree(repository)
    execution = ExecutionSummary(
        command=list(result.command),
        image_id=result.image_id,
        returncode=result.returncode,
        stdout_sha256=sha256(result.stdout.encode("utf-8")).hexdigest(),
        stderr_sha256=sha256(result.stderr.encode("utf-8")).hexdigest(),
        stdout_excerpt=result.stdout[-4000:],
        stderr_excerpt=result.stderr[-4000:],
        pre_execution_tree_sha256=provenance.tree_digest,
        post_execution_tree_sha256=post_provenance.tree_digest,
        source_unchanged=provenance.tree_digest == post_provenance.tree_digest,
    )

    if not execution.source_unchanged:
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            environment=environment,
            evidence_candidates=evidence,
            command_candidates=commands,
            execution=execution,
            record=_unable_record(
                claim,
                policy,
                rationale="Source repository changed during verification; verdict suppressed.",
            ),
        )

    if result.returncode != 0:
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            environment=environment,
            evidence_candidates=evidence,
            command_candidates=commands,
            execution=execution,
            record=_unable_record(
                claim,
                policy,
                rationale=f"Research command exited with status {result.returncode}.",
            ),
        )

    observation_candidates: list[ObservationCandidate] = []
    if json_path is not None:
        observation = extract_json_observation(
            result.stdout,
            json_path,
            scale=observation_scale,
        )
        observation_method = "explicit_json_path"
        observation_locator = json_path
        missing_rationale = (
            f"Execution succeeded, but JSON path {json_path!r} did not resolve "
            "to a numeric observation."
        )
    else:
        observation_candidates = extract_observation_candidates(result.stdout, claim)
        observation = select_unambiguous_observation(observation_candidates)
        observation_method = "semantic_stdout"
        observation_locator = None
        missing_rationale = (
            "Execution succeeded, but AgnXiv could not identify an unambiguous "
            "observation for this claim without using the reported answer as a hint."
        )

    if observation is None:
        record = _unable_record(
            claim,
            policy,
            rationale=missing_rationale,
        )
    else:
        observation.output_digest = execution.stdout_sha256
        record = verify_numeric_claim(claim, [observation], policy)

    return VerificationBundle(
        claim=claim,
        manuscript=manuscript,
        provenance=provenance,
        environment=environment,
        evidence_candidates=evidence,
        command_candidates=commands,
        execution=execution,
        observation_method=observation_method,
        observation_locator=observation_locator,
        observation_candidates=observation_candidates,
        record=record,
    )
