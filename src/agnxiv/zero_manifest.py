"""Fail-closed zero-manifest verification of numeric claims in real papers.

There are two distinct executions:
  1. discovery: run the documented command without giving locator discovery
     access to any reported numeric value;
  2. verification: rerun with the frozen, explicit stdout regex.

A command succeeding, or an ambiguous metric, is never a positive verdict.
"""
from __future__ import annotations

import re
import shlex
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from .auto import AutoPlan, build_auto_plan
from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .models import Claim
from .pipeline import VerificationBundle, verify_with_command
from .sandbox import SandboxError, execute_in_docker

_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_LINE = re.compile(
    rf"^\s*(?P<label>[A-Za-z][A-Za-z0-9 _'./-]{{1,65}}?)"
    rf"\s*[:=]\s*(?P<value>{_FLOAT})(?P<percent>%)?\s*$"
)
_ALIASES = {
    "split_half_r": {"split half r", "split half reliability"},
    "spearman_brown": {"spearman brown", "spearman brown coefficient"},
    "cohens_d": {"cohens d", "cohen d", "cohens d profile"},
    "accuracy": {"accuracy", "acc", "classification accuracy"},
    "f1": {"f1", "f1 score", "micro f1", "macro f1"},
    "mae": {"mae", "mean absolute error"},
    "mse": {"mse", "mean squared error"},
    "rmse": {"rmse", "root mean squared error"},
    "auroc": {"auroc", "roc auc"},
    "auc": {"auc"},
    "bleu": {"bleu", "bleu 4"},
    "precision": {"precision"},
    "recall": {"recall"},
    "latency": {"latency"},
    "runtime": {"runtime", "run time"},
    "throughput": {"throughput"},
}
_PREFERRED = tuple(_ALIASES)
_NUMBER = re.compile(_FLOAT + r"%?")
_BAD_LABELS = ("reported", "reference", "expected", "target", "claimed", "paper value")


def _normalize_label(label: str) -> str:
    return " ".join(re.findall(r"[a-z]+|\d+", label.lower().replace("'", "")))


class FrozenLocator(BaseModel):
    claim_id: str
    metric: str
    regex: str
    scale: float
    label: str
    discovery_stdout_sha256: str


class ZeroManifestOutcome(BaseModel):
    status: str
    reason: str
    plan: AutoPlan
    frozen_locator: FrozenLocator | None = None
    bundle: VerificationBundle | None = None


def discover_frozen_locator(stdout: str, claims: list[Claim]) -> FrozenLocator | None:
    """Bind only unique paper metrics to unique observed key/value stdout lines.

    Never compare a candidate observation to a reported answer when selecting.
    Do not synthesize a numeric regex from the observed numeric value.
    """
    lines: dict[str, list[tuple[str, bool]]] = {}
    for line in stdout.splitlines():
        match = _LINE.fullmatch(line)
        if not match:
            continue
        label = match.group("label").strip()
        key = _normalize_label(label)
        if any(bad in key for bad in _BAD_LABELS):
            continue
        if not key or not match.group("value"):
            continue
        lines.setdefault(key, []).append((label, match.group("percent") == "%"))

    eligible: list[tuple[int, Claim, str, bool]] = []
    for rank, metric in enumerate(_PREFERRED):
        matches = [
            claim for claim in claims
            if claim.metric == metric and claim.reported_value is not None
        ]
        # Multiple manuscript values for the same metric are not safely
        # distinguishable with only a metric label. Do not cherry-pick one.
        if len(matches) != 1:
            continue
        possible = [
            item
            for key, values in lines.items()
            if key in _ALIASES[metric]
            for item in values
        ]
        if len(possible) != 1:
            continue
        label, percent = possible[0]
        claim = matches[0]
        # A percentage display is a fraction claim only when the paper
        # explicitly reports the corresponding percentage unit.
        if percent and claim.unit != "fraction":
            continue
        if not percent and claim.unit == "fraction":
            # Printed 0.51 can represent a fraction, but 51 without "%"
            # must never be rescaled based on the expected paper value.
            pass
        eligible.append((rank, claim, label, percent))

    if not eligible:
        return None

    # Fixed precedence based on metric identity, not observed or expected values.
    _, claim, label, percent = min(eligible, key=lambda row: row[0])
    regex = (
        r"^\s*" + re.escape(label) + r"\s*[:=]\s*"
        + rf"(?P<value>{_FLOAT})"
        + (r"%" if percent else "")
        + r"\s*$"
    )
    return FrozenLocator(
        claim_id=claim.id,
        metric=claim.metric or "",
        regex=regex,
        scale=0.01 if percent else 1.0,
        label=label,
        discovery_stdout_sha256=sha256(stdout.encode("utf-8")).hexdigest(),
    )


def _claims(path: Path) -> list[Claim]:
    if path.suffix.lower() == ".pdf":
        return extract_claims_from_pdf(path)
    return extract_quantitative_claims(
        path.read_text(encoding="utf-8"), manuscript=path.name
    )


def run_zero_manifest(
    manuscript: str | Path,
    repository: str | Path,
    *,
    image: str,
) -> ZeroManifestOutcome:
    """Execute one documented workflow only when every prerequisite is safe."""
    paper = Path(manuscript).resolve()
    repo = Path(repository).resolve()
    plan = build_auto_plan(paper, repo)
    stages = {stage.name: stage.complete for stage in plan.stages}
    prerequisites = (
        "paper_ingest",
        "claim_compilation",
        "repository_mapping",
        "environment_inference",
        "command_discovery",
        "workflow_ordering",
        "artifact_resolution",
    )
    unmet = [stage for stage in prerequisites if not stages.get(stage)]
    if plan.blockers or unmet:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason="Unsafe or incomplete research plan: "
            + "; ".join([*plan.blockers, *unmet]),
            plan=plan,
        )

    draft = plan.draft_spec
    if draft is None:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason="No documented executable workflow.",
            plan=plan,
        )
    sequence = draft.runtime.command_sequence()
    command = (
        sequence[0] if len(sequence) == 1
        else ["sh", "-lc", " && ".join(shlex.join(row) for row in sequence)]
    )
    try:
        discovery = execute_in_docker(
            image=image,
            repository=repo,
            command=command,
        )
    except SandboxError as exc:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason=f"Sandboxed discovery could not run: {exc}",
            plan=plan,
        )
    if discovery.returncode != 0:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason=f"Discovery execution exited with {discovery.returncode}.",
            plan=plan,
        )

    locator = discover_frozen_locator(discovery.stdout, _claims(paper))
    if locator is None:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason="No unique, answer-blind paper-claim ↔ stdout-metric locator.",
            plan=plan,
        )
    selected = next(
        (row for row in _claims(paper) if row.id == locator.claim_id), None
    )
    if selected is None:
        return ZeroManifestOutcome(
            status="UNABLE_TO_VERIFY",
            reason="Frozen claim no longer matches manuscript.",
            plan=plan,
        )

    # The claim's reported value is consulted only *after* the regex has
    # been frozen. The verification worker performs an independent rerun.
    bundle = verify_with_command(
        selected,
        repo,
        image=image,
        command=command,
        policy=plan.draft_spec.policy.__class__(
            kind="absolute" if selected.unit == "fraction" else "relative",
            tolerance=0.01,
        ),
        manuscript_path=paper,
        output_regex=locator.regex,
        observation_scale=locator.scale,
    )
    return ZeroManifestOutcome(
        status=bundle.record.verdict.value,
        reason=bundle.record.rationale,
        plan=plan,
        frozen_locator=locator,
        bundle=bundle,
    )
