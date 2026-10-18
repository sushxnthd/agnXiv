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

_FILE_SUFFIXES = (
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
    ".embeddings",
    ".embedding",
    ".txt",
)

_OUTPUT_FLAGS = {
    "--output",
    "--out",
    "-o",
}

_INPUT_FLAGS = {
    "--input",
    "--emb",
    "--embedding",
    "--embeddings",
    "--network",
    "--data",
    "--dataset",
    "--labels",
    "--checkpoint",
    "--model",
}


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
    score = 0.10

    if claim.reported_value is not None:
        score += 0.15
    if claim.metric:
        score += 0.25
    if claim.unit == "fraction":
        score += 0.15
    elif claim.unit:
        score += 0.05
    if claim.reported_uncertainty is not None:
        score += 0.05
    if claim.source.page is not None:
        score += 0.05

    lower = claim.text.lower()
    if any(
        token in lower
        for token in (
            "achiev",
            "outperform",
            "improv",
            "reduc",
            "increase",
            "decrease",
            "significant",
            "result",
            "score",
        )
    ):
        score += 0.10

    if evidence:
        score += min(0.20, 0.08 + evidence[0].score * 0.12)

    numeric_tokens = re.findall(
        r"(?<![A-Za-z0-9_.])[-+]?\d+(?:\.\d+)?%?",
        claim.text,
    )
    word_tokens = re.findall(r"[A-Za-z]{2,}", claim.text)

    if len(numeric_tokens) >= 6 and len(numeric_tokens) >= max(4, len(word_tokens) // 2):
        score -= 0.22
    elif len(numeric_tokens) >= 4:
        score -= 0.08

    if any(
        phrase in lower
        for phrase in (
            "for reference",
            "included for reference",
            "common practice",
            "we follow",
            "baseline result",
        )
    ):
        score -= 0.14

    if any(
        phrase in lower
        for phrase in (
            "our model",
            "our method",
            "our approach",
            "our proposed",
            "we achieve",
            "we obtain",
            "we outperform",
            "proposed method",
        )
    ):
        score += 0.12

    if "state-of-the-art" in lower or "sota" in lower:
        score += 0.06

    if len(claim.text) > 420:
        score -= 0.06

    return min(max(score, 0.0), 1.0)


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


def _option_paths(
    command: CommandCandidate,
    flags: set[str],
) -> set[str]:
    values: set[str] = set()
    tokens = command.command

    for index, token in enumerate(tokens[:-1]):
        if token not in flags:
            continue
        value = tokens[index + 1].strip("'\"")
        if value.lower().endswith(_FILE_SUFFIXES):
            values.add(value)

    return values


def _workflow_commands(
    commands: list[CommandCandidate],
    repository: Path,
) -> tuple[list[CommandCandidate], list[str], bool]:
    """Order a small documented command DAG and report unresolved input files."""
    selected = [candidate for candidate in commands if candidate.score >= 0.84]
    if not selected:
        return [], [], False

    produced_by: dict[str, int] = {}
    inputs_by_index: dict[int, set[str]] = {}

    for index, candidate in enumerate(selected):
        for output in _option_paths(candidate, _OUTPUT_FLAGS):
            produced_by[output] = index
        inputs_by_index[index] = _option_paths(candidate, _INPUT_FLAGS)

    dependencies: dict[int, set[int]] = {index: set() for index in range(len(selected))}
    missing: list[str] = []

    for index, inputs in inputs_by_index.items():
        for value in inputs:
            producer = produced_by.get(value)
            if producer is not None and producer != index:
                dependencies[index].add(producer)
                continue
            if not (repository / value).exists():
                missing.append(value)

    ordered: list[CommandCandidate] = []
    remaining = set(range(len(selected)))

    while remaining:
        ready = [
            index
            for index in sorted(remaining)
            if not (dependencies[index] & remaining)
        ]
        if not ready:
            return selected, sorted(set(missing)), False

        for index in ready:
            ordered.append(selected[index])
            remaining.remove(index)

    has_explicit_dependency = any(dependencies.values())
    order_confident = len(selected) == 1 or has_explicit_dependency
    return ordered, sorted(set(missing)), order_confident


def _default_policy(claim: Claim) -> VerificationPolicy:
    if claim.unit == "fraction":
        return VerificationPolicy(kind="absolute", tolerance=0.01)
    return VerificationPolicy(kind="relative", tolerance=0.01)


def build_auto_plan(
    manuscript: str | Path,
    repository: str | Path,
) -> AutoPlan:
    """Build a conservative zero-manifest verification plan."""
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
    for claim in raw_claims[:120]:
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
        blockers.append(
            "No material quantitative claims were extracted from the manuscript."
        )
    if not commands:
        blockers.append(
            "No reproducibility/evaluation command could be discovered."
        )
    if environment.confidence < 0.55:
        blockers.append(
            "The software environment could not be inferred with adequate confidence."
        )

    if warnings:
        blockers.append(
            "The repository documents historical dependency/version sensitivity; "
            "exact reproduction requires environment archaeology."
        )

    workflow, missing_inputs, workflow_order_confident = _workflow_commands(
        commands,
        repo,
    )

    if missing_inputs:
        blockers.append(
            "Documented command references missing local inputs: "
            + ", ".join(missing_inputs)
        )

    if len(workflow) > 1 and not workflow_order_confident:
        blockers.append(
            "Multiple high-confidence research commands were discovered, but "
            "their execution order could not be inferred safely."
        )
    elif len(workflow) > 1:
        warnings.append(
            f"A {len(workflow)}-stage research workflow was ordered by file dataflow."
        )

    top_claim = ranked[0] if ranked else None

    draft_spec: VerificationSpec | None = None
    observation_safe = False

    if top_claim is not None and workflow:
        observation = ObservationLocator(kind="semantic_stdout")
        runtime = (
            RuntimeSpec(
                image=environment.base_image,
                command=workflow[0].command,
            )
            if len(workflow) == 1
            else RuntimeSpec(
                image=environment.base_image,
                commands=[candidate.command for candidate in workflow],
            )
        )

        draft_spec = VerificationSpec(
            repository=".",
            claim=top_claim.claim,
            policy=_default_policy(top_claim.claim),
            runtime=runtime,
            manuscript=manuscript_path.name,
            observation=observation,
        )
        warnings.append(
            "A draft manifest was generated with semantic stdout parsing; "
            "an explicit JSON/regex locator should be established before "
            "unattended certification."
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
            name="workflow_ordering",
            complete=bool(workflow) and workflow_order_confident,
            detail=(
                f"{len(workflow)} command stage(s) ordered"
                if workflow
                else "no workflow available"
            ),
        ),
        AutomationStage(
            name="artifact_resolution",
            complete=not missing_inputs,
            detail=(
                "documented external inputs resolved or generated by prior stages"
                if not missing_inputs
                else f"{len(missing_inputs)} missing input(s)"
            ),
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
