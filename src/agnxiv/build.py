from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .provenance import sha256_file
from .sandbox import (
    SandboxError,
    is_immutable_image_digest_ref,
    resolve_local_image_digest_ref,
    resolve_local_image_id,
)


class EnvironmentBuildError(RuntimeError):
    """A controlled failure while constructing a research runtime."""


class BuildPlan(BaseModel):
    builder: str = "python-requirements"
    base_image: str
    dependency_file: str | None
    dependency_sha256: str | None
    dependency_precision: Literal[
        "base-only",
        "floating",
        "version-pinned",
        "hash-pinned",
    ]
    dockerfile: str
    network_required: bool
    safe_manifest_only: bool
    rejected_reasons: list[str] = Field(default_factory=list)

    @property
    def plan_id(self) -> str:
        payload = "\n".join(
            [
                self.builder,
                self.base_image,
                self.dependency_file or "",
                self.dependency_sha256 or "",
                self.dependency_precision,
                self.dockerfile,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BuildResult(BaseModel):
    plan: BuildPlan
    image_ref: str
    image_id: str
    base_image_id: str
    stdout_sha256: str
    stderr_sha256: str


_UNSAFE_REQUIREMENT_MARKERS = (
    "-e ",
    "--editable",
    "git+",
    "hg+",
    "svn+",
    "bzr+",
    "file:",
    "../",
    "./",
    "http://",
    "https://",
    "--index-url",
    "--extra-index-url",
    "--find-links",
    "--trusted-host",
)

_EXACT_REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[^\s;\\]+"
)
_SHA256_REQUIREMENT_HASH_RE = re.compile(r"--hash=sha256:[0-9a-fA-F]{64}(?:\s|$)")


def _active_requirement_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Pip treats a hash mark preceded by whitespace as an inline comment.
        # Evidence inside that discarded suffix must not satisfy hash pinning.
        effective = re.split(r"\s+#", stripped, maxsplit=1)[0].rstrip()
        if effective:
            lines.append(effective)
    return lines


def classify_dependency_precision(path: str | Path) -> Literal[
    "floating",
    "version-pinned",
    "hash-pinned",
]:
    """Classify how precisely a requirements file identifies dependencies."""
    requirement_path = Path(path)
    lines = _active_requirement_lines(requirement_path)
    logical_lines: list[str] = []
    continuation: list[str] = []
    dangling_continuation = False
    for line in lines:
        continued = line.endswith("\\")
        continuation.append(line[:-1].strip() if continued else line)
        if continued:
            dangling_continuation = True
            continue
        logical_lines.append(" ".join(continuation))
        continuation = []
        dangling_continuation = False

    if continuation:
        logical_lines.append(" ".join(continuation))

    package_lines = [
        line
        for line in logical_lines
        if not line.startswith("-") and not line.startswith("\\")
    ]

    if not package_lines:
        return "floating"

    all_exact = all(_EXACT_REQUIREMENT_RE.match(line) for line in package_lines)
    if not all_exact:
        return "floating"

    if dangling_continuation:
        return "version-pinned"

    every_package_hashed = all(
        _SHA256_REQUIREMENT_HASH_RE.search(line) for line in package_lines
    )
    return "hash-pinned" if every_package_hashed else "version-pinned"


def audit_requirements(path: str | Path) -> list[str]:
    """Return reasons a requirements file needs stronger build isolation."""
    requirement_path = Path(path)
    reasons: list[str] = []

    for line_number, raw in enumerate(
        requirement_path.read_text(encoding="utf-8", errors="ignore").splitlines(),
        start=1,
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        lower = line.lower()
        for marker in _UNSAFE_REQUIREMENT_MARKERS:
            if marker in lower:
                reasons.append(
                    f"line {line_number}: unsupported dependency source or option: {marker}"
                )
                break

    return reasons


def plan_python_environment(
    repository: str | Path,
    *,
    base_image: str = "python:3.11-slim",
    dependency_file: str | Path | None = None,
) -> BuildPlan:
    """Create a dependency-only environment build plan.

    The generated context contains dependency metadata only, never the research
    repository itself.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    if dependency_file is None:
        dependency_relative = Path("requirements.txt")
    else:
        dependency_relative = Path(dependency_file)
        if dependency_relative.is_absolute() or ".." in dependency_relative.parts:
            raise ValueError("dependency file must be workspace-relative")
        if dependency_relative.suffix.lower() != ".txt":
            raise ValueError("only pip requirements text files are supported")

    requirements = root / dependency_relative
    if requirements.is_symlink():
        raise ValueError("dependency manifest symlinks are not allowed")
    if requirements.exists() and not requirements.is_file():
        raise ValueError("dependency manifest is not a regular file")

    if not requirements.exists():
        if dependency_file is not None:
            raise ValueError(
                f"dependency manifest does not exist: {dependency_relative.as_posix()}"
            )
        return BuildPlan(
            base_image=base_image,
            dependency_file=None,
            dependency_sha256=None,
            dependency_precision="base-only",
            dockerfile=(
                f"FROM {base_image}\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
                "WORKDIR /workspace\n"
            ),
            network_required=False,
            safe_manifest_only=True,
        )

    rejected = audit_requirements(requirements)
    dependency_precision = classify_dependency_precision(requirements)
    hash_enforcement = (
        " --require-hashes" if dependency_precision == "hash-pinned" else ""
    )
    dockerfile = (
        f"FROM {base_image}\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "COPY requirements.txt /tmp/requirements.txt\n"
        "RUN python -m pip install --no-cache-dir"
        f"{hash_enforcement} -r /tmp/requirements.txt\n"
        "WORKDIR /workspace\n"
    )
    return BuildPlan(
        base_image=base_image,
        dependency_file=dependency_relative.as_posix(),
        dependency_sha256=sha256_file(requirements),
        dependency_precision=dependency_precision,
        dockerfile=dockerfile,
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
    )


def bind_plan_to_immutable_base(
    plan: BuildPlan,
    immutable_base: str,
) -> BuildPlan:
    """Replace the mutable Dockerfile base tag with its repository digest."""
    if not is_immutable_image_digest_ref(immutable_base):
        raise EnvironmentBuildError(
            "base image lacks a canonical immutable repository digest"
        )
    expected = f"FROM {plan.base_image}\n"
    if not plan.dockerfile.startswith(expected):
        raise EnvironmentBuildError("build plan has an unexpected base-image directive")
    dockerfile = f"FROM {immutable_base}\n" + plan.dockerfile[len(expected):]
    return plan.model_copy(
        update={"base_image": immutable_base, "dockerfile": dockerfile}
    )


def copy_frozen_dependency_manifest(
    source: str | Path,
    destination: str | Path,
    *,
    expected_sha256: str,
) -> None:
    """Copy a manifest into the private build context or fail on drift."""
    shutil.copyfile(source, destination)
    observed_sha256 = sha256_file(destination)
    if observed_sha256 != expected_sha256:
        raise EnvironmentBuildError(
            "dependency manifest changed after build planning; build rejected"
        )


def build_python_environment(
    repository: str | Path,
    *,
    base_image: str = "python:3.11-slim",
    dependency_file: str | Path | None = None,
    timeout_seconds: int = 1200,
) -> BuildResult:
    """Build a runtime without exposing research source to dependency installers."""
    root = Path(repository)
    plan = plan_python_environment(
        root,
        base_image=base_image,
        dependency_file=dependency_file,
    )

    if not plan.safe_manifest_only:
        reasons = "; ".join(plan.rejected_reasons)
        raise EnvironmentBuildError(
            "dependency manifest requires stronger isolation and was rejected: "
            + reasons
        )

    try:
        base_image_id_before = resolve_local_image_id(base_image)
        immutable_base = resolve_local_image_digest_ref(base_image)
    except (SandboxError, ValueError) as exc:
        raise EnvironmentBuildError(
            "base image must have local immutable identity before construction"
        ) from exc

    plan = bind_plan_to_immutable_base(plan, immutable_base)

    image_ref = f"agnxiv-env:{plan.plan_id[:24]}"

    with tempfile.TemporaryDirectory(prefix="agnxiv-build-") as temp:
        context = Path(temp)
        (context / "Dockerfile").write_text(plan.dockerfile, encoding="utf-8")

        if plan.dependency_file is not None:
            if plan.dependency_sha256 is None:
                raise EnvironmentBuildError(
                    "dependency manifest lacks a frozen content digest"
                )
            copy_frozen_dependency_manifest(
                root / plan.dependency_file,
                context / "requirements.txt",
                expected_sha256=plan.dependency_sha256,
            )

        command = [
            "docker",
            "build",
            "--pull=false",
            "--network",
            "default" if plan.network_required else "none",
            "--tag",
            image_ref,
            str(context),
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentBuildError(f"environment build failed: {exc}") from exc

    if completed.returncode != 0:
        message = completed.stderr[-4000:] or completed.stdout[-4000:]
        raise EnvironmentBuildError(
            f"environment build exited with {completed.returncode}: {message}"
        )

    base_image_id_after = resolve_local_image_id(base_image)
    if base_image_id_after != base_image_id_before:
        raise EnvironmentBuildError(
            "base image changed during environment construction; build rejected"
        )

    image_id = resolve_local_image_id(image_ref)
    return BuildResult(
        plan=plan,
        image_ref=image_ref,
        image_id=image_id,
        base_image_id=base_image_id_before,
        stdout_sha256=hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        stderr_sha256=hashlib.sha256(completed.stderr.encode("utf-8")).hexdigest(),
    )
