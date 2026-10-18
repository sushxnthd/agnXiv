from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .environment import EnvironmentSpec, infer_python_environment
from .evidence import EvidenceCandidate, map_claim_to_repository
from .models import Claim, VerificationPolicy
from .planner import CommandCandidate, discover_commands
from .spec import ObservationLocator, RuntimeSpec, VerificationSpec


class AutomationStage(BaseModel):
    name: str
    complete: bool
    detail: str


class RankedClaim(BaseModel):
    claim: Claim
    score: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceCandidate] = Field(default_factory=list)


class AutoPlan(BaseModel):
    schema_version: str = "agnxiv.auto/1"
    manuscript: str
    repository: str
    environment: EnvironmentSpec
    claims: list[RankedClaim]
    commands: list[CommandCandidate]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stages: list[AutomationStage]
    automation_score: float = Field(ge=0.0, le=1.0)
    safe_to_execute: bool
    draft_spec: VerificationSpec | None = None


_HISTORICAL_ENV_PATTERNS = (
    r"older version",
    r"specific version",
    r"version\s+[0-9]+(?:\.[0-9]+)+",
    r"exact(?:ly)? reproduce",
    r"reproduc(?:e|ibility).{0,80}(?:version|dependency|environment)",
)

_EXTERNAL_INPUT_SUFFIXES = (
    ".mat",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".pkl",
    ".pickle",
    ".npy",
    ".npz",
    ".pt",
    ".pth",
    ".ckpt",
    ".h5",
    ".hdf5",
)


def _read_manuscript(path: Path) -> list[Claim]:
    if path.suffix.lower() == ".pdf":
        return extract_claims_from_pdf(path)
    return extract_quantitative_claims(
        path.read_text(encoding="utf-8", errors="ignore"),
        manuscript=path.name,
    )


def _read_readme(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _rank_claim(claim: Claim, evidence: list[EvidenceCandidate]) -> float:
    score = 0.15
    if claim.reported_value is not None:
        score += 0.20
    if claim.metric:
        score += 0.20
    if claim.unit:
        score += 0.05
    if claim.source.page is not None:
        score += 0.05
    if evidence:
        score += min(0.35, 0.20 + evidence[0].score * 0.15)
    return min(score, 1.0)


def _historical_environment_warnings(readme: str) -> list[str]:
    warnings: list[str] = []
    lower = readme.lower()
    for pattern in _HISTORICAL_ENV_PATTERNS:
        match = re.search(pattern, lower, flags=re.DOTALL)
        if not match:
            continue
        start = max(0, match.start() - 120)
        end = min(len(readme), match.end() + 180)
        excerpt = " ".join(readme[start:end].split())
        if excerpt and excerpt not in warnings:
            warnings.append(excerpt)
    return warnings[:4]


def _missing_command_inputs(
    command: CommandCandidate,
    repository: Path,
) -> list[str]:
    missing: list[str] = []
    for token in command.command:
        cleaned = token.strip("'\"")
        if not cleaned.lower().endswith(_EXTERNAL_INPUT_SUFFIXES):
            continue
        candidate = repository / cleaned
        if not candidate.exists():
            missing.append(cleaned)
    return missing


def _default_policy(claim: Claim) -> VerificationPolicy:
    if claim.unit == "fraction":
        return VerificationPolicy(kind="absolute", tolerance=0.01)
    return VerificationPolicy(kind="relative", tolerance=0.01)


def build_auto_plan(
    manuscript: str | Path,
    repository: str | Path,
) -> AutoPlan:
    """Build a conservative zero-manifest verification plan.

    The planner may generate a draft spec, but only marks it safe to execute
    when the paper, environment, command, and observation paths are sufficiently
    constrained. Discovery confidence never becomes a verification verdict.
    """
    manuscript_path = Path(manuscript).resolve()
    repo = Path(repository).resolve()
    if not manuscript_path.is_file():
        raise ValueError(f"manuscript path is not a file: {manuscript_path}")
    if not repo.is_dir():
        raise ValueError(f"repository path is not a directory: {repo}")

    raw_claims = _read_manuscript(manuscript_path)
    environment = infer_python_environment(repo)
    commands = discover_commands(repo)
    readme = _read_readme(repo)

    ranked: list[RankedClaim] = []
    for claim in raw_claims[:80]:
        evidence = map_claim_to_repository(claim, repo, limit=5)
        ranked.append(
            RankedClaim(
                claim=claim,
                score=_rank_claim(claim, evidence),
                evidence=evidence,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)

    blockers: list[str] = []
    warnings = _historical_environment_warnings(readme)

    if not raw_claims:
        blockers.append("No material quantitative claims were extracted from the manuscript.")
    if not commands:
        blockers.append("No reproducibility/evaluation command could be discovered.")
    if environment.confidence < 0.55:
        blockers.append("The software environment could not be inferred with adequate confidence.")

    if warnings:
        blockers.append(
            "The repository documents historical dependency/version sensitivity; "
            "exact reproduction requires environment archaeology."
        )

    high_commands = [candidate for candidate in commands if candidate.score >= 0.84]
    if len(high_commands) > 1:
        blockers.append(
            "Multiple high-confidence research commands were discovered; "
            "the workflow may be multi-stage."
        )

    for candidate in high_commands[:3]:
        missing = _missing_command_inputs(candidate, repo)
        if missing:
            blockers.append(
                "Documented command references missing local inputs: " + ", ".join(missing)
            )

    top_claim = ranked[0] if ranked else None
    top_command = commands[0] if commands else None

    draft_spec: VerificationSpec | None = None
    observation_safe = False
    if top_claim is not None and top_command is not None:
        observation = ObservationLocator(kind="semantic_stdout")
        draft_spec = VerificationSpec(
            repository=".",
            claim=top_claim.claim,
            policy=_default_policy(top_claim.claim),
            runtime=RuntimeSpec(
                image=environment.base_image,
                command=top_command.command,
            ),
            manuscript=manuscript_path.name,
            observation=observation,
        )
        observation_safe = False
        warnings.append(
            "A draft manifest was generated with semantic stdout parsing; "
            "an explicit JSON/regex locator should be established before unattended certification."
        )

    stages = [
        AutomationStage(
            name="paper_ingest",
            complete=manuscript_path.is_file(),
            detail="manuscript available locally",
        ),
        AutomationStage(
            name="claim_compilation",
            complete=bool(raw_claims),
            detail=f"{len(raw_claims)} candidate quantitative claims extracted",
        ),
        AutomationStage(
            name="repository_mapping",
            complete=bool(ranked and ranked[0].evidence),
            detail=(
                f"top claim has {len(ranked[0].evidence)} evidence candidates"
                if ranked
                else "no ranked claims"
            ),
        ),
        AutomationStage(
            name="environment_inference",
            complete=environment.confidence >= 0.55,
            detail=f"environment confidence {environment.confidence:.2f}",
        ),
        AutomationStage(
            name="command_discovery",
            complete=bool(commands),
            detail=f"{len(commands)} candidate research commands discovered",
        ),
        AutomationStage(
            name="artifact_resolution",
            complete=not any("missing local inputs" in item for item in blockers),
            detail="documented command inputs checked against repository",
        ),
        AutomationStage(
            name="observation_locator",
            complete=observation_safe,
            detail="explicit output locator not yet proven automatically",
        ),
        AutomationStage(
            name="verification_spec",
            complete=draft_spec is not None,
            detail="draft spec generated" if draft_spec else "draft spec unavailable",
        ),
    ]
    automation_score = sum(stage.complete for stage in stages) / len(stages)

    safe_to_execute = (
        draft_spec is not None
        and observation_safe
        and not blockers
    )

    return AutoPlan(
        manuscript=str(manuscript_path),
        repository=str(repo),
        environment=environment,
        claims=ranked[:20],
        commands=commands,
        blockers=list(dict.fromkeys(blockers)),
        warnings=list(dict.fromkeys(warnings)),
        stages=stages,
        automation_score=automation_score,
        safe_to_execute=safe_to_execute,
        draft_spec=draft_spec,
    )
