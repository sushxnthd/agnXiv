from __future__ import annotations

import json
import math
import shlex
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import Claim, VerificationPolicy
from .outputs import safe_regex_pattern
from .pipeline import VerificationBundle, verify_with_command
from .provenance import sha256_file

_MAX_SPEC_BYTES = 1024 * 1024
_MAX_PATH_CHARS = 1024
_MAX_LOCATOR_CHARS = 1024
_MAX_COMMANDS = 16
_MAX_COMMAND_ARGS = 128
_MAX_COMMAND_ARG_CHARS = 4096
_MAX_COMMAND_TOTAL_CHARS = 64 * 1024
_MAX_ARTIFACTS = 64
_MAX_CLAIM_TEXT_CHARS = 16 * 1024


class ObservationLocator(BaseModel):
    kind: Literal["json_path", "regex", "semantic_stdout"] = "semantic_stdout"
    value: str | None = Field(default=None, max_length=_MAX_LOCATOR_CHARS)
    scale: float = 1.0

    @model_validator(mode="after")
    def validate_locator(self) -> ObservationLocator:
        if self.kind in {"json_path", "regex"} and not self.value:
            raise ValueError(f"{self.kind} observation requires a locator value")
        if self.kind == "semantic_stdout" and self.value is not None:
            raise ValueError("semantic_stdout observation does not accept a locator value")
        if self.kind == "regex" and self.value and not safe_regex_pattern(self.value):
            raise ValueError("regex observation uses an unsafe or unsupported pattern")
        if not math.isfinite(self.scale) or abs(self.scale) > 1_000_000:
            raise ValueError("observation scale must be finite and reasonably bounded")
        return self


class RuntimeSpec(BaseModel):
    image: str = Field(min_length=1, max_length=256)
    command: list[str] | None = None
    commands: list[list[str]] | None = None

    @model_validator(mode="after")
    def validate_commands(self) -> RuntimeSpec:
        has_command = bool(self.command)
        has_commands = bool(self.commands)
        if has_command == has_commands:
            raise ValueError("runtime requires exactly one of command or commands")
        sequence = self.commands if self.commands else ([self.command] if self.command else [])
        if self.commands and any(not command for command in self.commands):
            raise ValueError("runtime commands may not be empty")
        if len(sequence) > _MAX_COMMANDS:
            raise ValueError(f"runtime may contain at most {_MAX_COMMANDS} commands")
        total_chars = 0
        for command in sequence:
            assert command is not None
            if len(command) > _MAX_COMMAND_ARGS:
                raise ValueError(
                    f"runtime command may contain at most {_MAX_COMMAND_ARGS} arguments"
                )
            for argument in command:
                if not isinstance(argument, str) or not argument:
                    raise ValueError("runtime command arguments must be non-empty strings")
                if len(argument) > _MAX_COMMAND_ARG_CHARS:
                    raise ValueError("runtime command argument is too long")
                if "\x00" in argument or "\n" in argument or "\r" in argument:
                    raise ValueError("runtime command arguments may not contain control separators")
                total_chars += len(argument)
        if total_chars > _MAX_COMMAND_TOTAL_CHARS:
            raise ValueError("runtime command sequence is too large")
        return self

    def command_sequence(self) -> list[list[str]]:
        if self.commands:
            return self.commands
        assert self.command is not None
        return [self.command]


class VerificationSpec(BaseModel):
    schema_version: Literal["agnxiv.spec/1"] = "agnxiv.spec/1"
    repository: str = Field(default=".", min_length=1, max_length=_MAX_PATH_CHARS)
    claim: Claim
    policy: VerificationPolicy
    runtime: RuntimeSpec
    manuscript: str | None = Field(default=None, max_length=_MAX_PATH_CHARS)
    artifacts: list[str] = Field(default_factory=list, max_length=_MAX_ARTIFACTS)
    observation: ObservationLocator = Field(default_factory=ObservationLocator)

    @model_validator(mode="after")
    def validate_manifest_bounds(self) -> VerificationSpec:
        if len(self.claim.id) > 256:
            raise ValueError("claim id is too long")
        if len(self.claim.text) > _MAX_CLAIM_TEXT_CHARS:
            raise ValueError("claim text is too long")
        for value in (self.claim.metric, self.claim.unit):
            if value is not None and len(value) > 256:
                raise ValueError("claim metric/unit is too long")
        if self.claim.reported_value is not None and not math.isfinite(
            self.claim.reported_value
        ):
            raise ValueError("reported claim value must be finite")
        if not math.isfinite(self.policy.tolerance):
            raise ValueError("verification tolerance must be finite")
        if self.policy.minimum_repetitions > 1000:
            raise ValueError("verification repetitions are unreasonably large")
        for artifact in self.artifacts:
            if not artifact or len(artifact) > _MAX_PATH_CHARS:
                raise ValueError("artifact path is empty or too long")
        return self


def load_verification_spec(path: str | Path) -> VerificationSpec:
    """Load one versioned AgnXiv verification manifest."""
    spec_path = Path(path)
    if spec_path.is_symlink() or not spec_path.is_file():
        raise ValueError("verification manifest must be a regular non-symlink file")
    try:
        size = spec_path.stat().st_size
    except OSError as exc:
        raise ValueError("verification manifest metadata is unavailable") from exc
    if size > _MAX_SPEC_BYTES:
        raise ValueError(
            f"verification manifest exceeds {_MAX_SPEC_BYTES} byte limit"
        )
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

    sequence = spec.runtime.command_sequence()
    command = (
        sequence[0]
        if len(sequence) == 1
        else [
            "sh",
            "-lc",
            " && ".join(shlex.join(item) for item in sequence),
        ]
    )

    bundle = verify_with_command(
        spec.claim,
        repository,
        image=image_override or spec.runtime.image,
        command=command,
        policy=spec.policy,
        manuscript_path=manuscript,
        artifact_paths=artifacts,
        json_path=json_path,
        output_regex=output_regex,
        observation_scale=spec.observation.scale,
    )
    bundle.verification_spec_sha256 = sha256_file(spec_path)
    return bundle
