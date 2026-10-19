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
    extract_regex_observation,
    select_unambiguous_observation,
)
from .planner import CommandCandidate, discover_commands
from .provenance import (
    ArtifactFingerprint,
    DocumentFingerprint,
    ProvenanceManifest,
    fingerprint_artifact,
    fingerprint_document,
    fingerprint_tree,
)
from .sandbox import ExecutionResult, SandboxError, SandboxLimits, execute_in_docker
from .verify import verify_numeric_claim


class ExecutionSummary(BaseModel):
    command: list[str]
    image_id: str
    artifact_mounts: list[str] = Field(default_factory=list)
    returncode: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_excerpt: str
    stderr_excerpt: str
    pre_execution_tree_sha256: str
    post_execution_tree_sha256: str
    source_unchanged: bool
    artifacts_unchanged: bool


class RuntimeBuildEvidence(BaseModel):
    """Content-bound description of the runtime construction used for execution."""

    builder: str
    plan_id: str
    dependency_file: str | None = None
    dependency_sha256: str | None = None
    dependency_precision: str
    base_image_id: str
    image_id: str


class VerificationBundle(BaseModel):
    schema_version: str = "agnxiv.bundle/0.7"
    verification_spec_sha256: str | None = None
    claim: Claim
    manuscript: DocumentFingerprint | None = None
    provenance: ProvenanceManifest
    artifacts: list[ArtifactFingerprint] = Field(default_factory=list)
    environment: EnvironmentSpec
    runtime_build: RuntimeBuildEvidence | None = None
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


def _fingerprint_artifacts(
    paths: list[str | Path] | None,
) -> list[ArtifactFingerprint]:
    return [fingerprint_artifact(path) for path in paths or []]


def _artifact_signatures(
    artifacts: list[ArtifactFingerprint],
) -> list[tuple[str, str, int, int]]:
    return [
        (artifact.kind, artifact.sha256, artifact.size_bytes, artifact.file_count)
        for artifact in artifacts
    ]


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
    artifact_paths: list[str | Path] | None = None,
    json_path: str | None = None,
    output_regex: str | None = None,
    observation_scale: float = 1.0,
    limits: SandboxLimits | None = None,
) -> VerificationBundle:
    """Execute one explicit research command and verify one numeric claim."""
    if json_path is not None and output_regex is not None:
        raise ValueError("json_path and output_regex are mutually exclusive")

    active_limits = limits or SandboxLimits()
    provenance, environment, evidence, commands = inspect_project(claim, repository)
    manuscript = (
        fingerprint_document(manuscript_path) if manuscript_path is not None else None
    )
    artifacts = _fingerprint_artifacts(artifact_paths)

    try:
        result: ExecutionResult = execute_in_docker(
            image=image,
            repository=repository,
            command=command,
            artifact_paths=artifact_paths,
            limits=active_limits,
        )
    except SandboxError as exc:
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            artifacts=artifacts,
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
    post_artifacts = _fingerprint_artifacts(artifact_paths)
    source_unchanged = provenance.tree_digest == post_provenance.tree_digest
    artifacts_unchanged = _artifact_signatures(artifacts) == _artifact_signatures(
        post_artifacts
    )

    execution = ExecutionSummary(
        command=list(result.command),
        image_id=result.image_id,
        artifact_mounts=[mount.container_path for mount in result.artifact_mounts],
        returncode=result.returncode,
        stdout_sha256=sha256(result.stdout.encode("utf-8")).hexdigest(),
        stderr_sha256=sha256(result.stderr.encode("utf-8")).hexdigest(),
        stdout_excerpt=result.stdout[-4000:],
        stderr_excerpt=result.stderr[-4000:],
        pre_execution_tree_sha256=provenance.tree_digest,
        post_execution_tree_sha256=post_provenance.tree_digest,
        source_unchanged=source_unchanged,
        artifacts_unchanged=artifacts_unchanged,
    )

    if not source_unchanged or not artifacts_unchanged:
        changed = []
        if not source_unchanged:
            changed.append("source repository")
        if not artifacts_unchanged:
            changed.append("external artifacts")
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            artifacts=artifacts,
            environment=environment,
            evidence_candidates=evidence,
            command_candidates=commands,
            execution=execution,
            record=_unable_record(
                claim,
                policy,
                rationale=(
                    "Evidence changed during verification; verdict suppressed: "
                    + ", ".join(changed)
                    + "."
                ),
            ),
        )

    if result.returncode != 0:
        return VerificationBundle(
            claim=claim,
            manuscript=manuscript,
            provenance=provenance,
            artifacts=artifacts,
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
    elif output_regex is not None:
        observation = extract_regex_observation(
            result.stdout,
            output_regex,
            scale=observation_scale,
        )
        observation_method = "explicit_regex"
        observation_locator = output_regex
        missing_rationale = (
            "Execution succeeded, but the declared regex did not resolve "
            "to exactly one numeric observation."
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
        artifacts=artifacts,
        environment=environment,
        evidence_candidates=evidence,
        command_candidates=commands,
        execution=execution,
        observation_method=observation_method,
        observation_locator=observation_locator,
        observation_candidates=observation_candidates,
        record=record,
    )
