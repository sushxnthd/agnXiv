from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

from .provenance import sha256_file


class BuildPlan(BaseModel):
    builder: str = "python-requirements"
    base_image: str
    dependency_file: str | None
    dependency_sha256: str | None
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
                self.dockerfile,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    "--index-url",
    "--extra-index-url",
    "--find-links",
)


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

    The generated context is intended to contain dependency metadata only, not
    the research repository itself.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    requirements = root / "requirements.txt"

    if not requirements.exists():
        return BuildPlan(
            base_image=base_image,
            dependency_file=None,
            dependency_sha256=None,
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
        dockerfile=dockerfile,
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
    )
