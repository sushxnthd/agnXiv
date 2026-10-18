from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import Claim, VerificationPolicy
from .pipeline import VerificationBundle, verify_with_command
from .provenance import sha256_file


class ObservationLocator(BaseModel):
    kind: Literal["json_path", "regex", "semantic_stdout"] = "semantic_stdout"
    value: str | None = None
    scale: float = 1.0

    @model_validator(mode="after")
    def validate_locator(self) -> ObservationLocator:
        if self.kind in {"json_path", "regex"} and not self.value:
            raise ValueError(f"{self.kind} observation requires a locator value")
        if self.kind == "semantic_stdout" and self.value is not None:
            raise ValueError("semantic_stdout observation does not accept a locator value")
        return self


class RuntimeSpec(BaseModel):
    image: str
    command: list[str] = Field(min_length=1)


class VerificationSpec(BaseModel):
    schema_version: Literal["agnxiv.spec/1"] = "agnxiv.spec/1"
    repository: str = "."
    claim: Claim
    policy: VerificationPolicy
    runtime: RuntimeSpec
    manuscript: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    observation: ObservationLocator = Field(default_factory=ObservationLocator)


def load_verification_spec(path: str | Path) -> VerificationSpec:
    """Load one versioned AgnXiv verification manifest."""
    spec_path = Path(path)
    return VerificationSpec.model_validate(
        json.loads(spec_path.read_text(encoding="utf-8"))
    )


def _resolve_workspace_path(base: Path, value: str, *, label: str) -> Path:
    """Resolve an untrusted manifest path without allowing workspace escape."""
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} path must be relative to the verification workspace")

    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"{label} path escapes the verification workspace: {value}"
        ) from exc
    return resolved


def execute_verification_spec(
    path: str | Path,
    *,
    image_override: str | None = None,
) -> VerificationBundle:
    """Resolve a manifest inside its own workspace and execute it."""
    spec_path = Path(path).resolve()
    spec = load_verification_spec(spec_path)
    base = spec_path.parent

    repository = _resolve_workspace_path(
        base,
        spec.repository,
        label="repository",
    )
    manuscript = (
        _resolve_workspace_path(base, spec.manuscript, label="manuscript")
        if spec.manuscript
        else None
    )
    artifacts = [
        _resolve_workspace_path(base, artifact, label="artifact")
        for artifact in spec.artifacts
    ]

    json_path = (
        spec.observation.value if spec.observation.kind == "json_path" else None
    )
    output_regex = (
        spec.observation.value if spec.observation.kind == "regex" else None
    )

    bundle = verify_with_command(
        spec.claim,
        repository,
        image=image_override or spec.runtime.image,
        command=spec.runtime.command,
        policy=spec.policy,
        manuscript_path=manuscript,
        artifact_paths=artifacts,
        json_path=json_path,
        output_regex=output_regex,
        observation_scale=spec.observation.scale,
    )
    bundle.verification_spec_sha256 = sha256_file(spec_path)
    return bundle
