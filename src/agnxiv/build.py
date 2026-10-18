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
from .sandbox import SandboxError, resolve_local_image_id


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


def _active_requirement_lines(path: Path) -> list[str]:
    return [
        raw.strip()
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]


def classify_dependency_precision(path: str | Path) -> Literal[
    "floating",
    "version-pinned",
    "hash-pinned",
]:
    """Classify how precisely a requirements file identifies dependencies."""
    requirement_path = Path(path)
    lines = _active_requirement_lines(requirement_path)
    package_lines = [
        line
        for line in lines
        if not line.startswith("-") and not line.startswith("\\")
    ]

    if not package_lines:
        return "floating"

    all_exact = all(_EXACT_REQUIREMENT_RE.match(line) for line in package_lines)
    if not all_exact:
        return "floating"

    has_hashes = any("--hash=sha256:" in line for line in lines)
    return "hash-pinned" if has_hashes else "version-pinned"


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
) -> BuildPlan:
    """Create a dependency-only environment build plan.

    The generated context contains dependency metadata only, never the research
    repository itself.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    requirements = root / "requirements.txt"

    if requirements.is_symlink():
        raise ValueError("requirements.txt symlinks are not allowed")

    if not requirements.exists():
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
    dockerfile = (
        f"FROM {base_image}\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "COPY requirements.txt /tmp/requirements.txt\n"
        "RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt\n"
        "WORKDIR /workspace\n"
    )
    return BuildPlan(
        base_image=base_image,
        dependency_file="requirements.txt",
        dependency_sha256=sha256_file(requirements),
        dependency_precision=classify_dependency_precision(requirements),
        dockerfile=dockerfile,
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
    )


def build_python_environment(
    repository: str | Path,
    *,
    base_image: str = "python:3.11-slim",
    timeout_seconds: int = 1200,
) -> BuildResult:
    """Build a runtime without exposing research source to dependency installers."""
    root = Path(repository)
    plan = plan_python_environment(root, base_image=base_image)

    if not plan.safe_manifest_only:
        reasons = "; ".join(plan.rejected_reasons)
        raise EnvironmentBuildError(
            "dependency manifest requires stronger isolation and was rejected: "
            + reasons
        )

    try:
        base_image_id_before = resolve_local_image_id(base_image)
    except (SandboxError, ValueError) as exc:
        raise EnvironmentBuildError(
            "base image must already exist locally before environment construction"
        ) from exc

    image_ref = f"agnxiv-env:{plan.plan_id[:24]}"

    with tempfile.TemporaryDirectory(prefix="agnxiv-build-") as temp:
        context = Path(temp)
        (context / "Dockerfile").write_text(plan.dockerfile, encoding="utf-8")

        if plan.dependency_file is not None:
            shutil.copyfile(
                root / plan.dependency_file,
                context / plan.dependency_file,
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
