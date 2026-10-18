from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxLimits:
    memory: str = "4g"
    cpus: float = 2.0
    pids: int = 256
    timeout_seconds: int = 600


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def docker_command(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    limits: SandboxLimits = SandboxLimits(),
) -> list[str]:
    """Build the locked-down Docker command used for research execution."""
    repo = Path(repository).resolve()
    if not repo.is_dir():
        raise ValueError(f"repository path is not a directory: {repo}")
    if not image.strip():
        raise ValueError("container image is required")
    if not command:
        raise ValueError("research command is required")

    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(limits.pids),
        "--memory", limits.memory,
        "--cpus", str(limits.cpus),
        "--mount", f"type=bind,src={repo},dst=/workspace,readonly",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
        "--workdir", "/workspace",
        image,
        *command,
    ]


def execute_in_docker(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    limits: SandboxLimits = SandboxLimits(),
) -> ExecutionResult:
    """Execute research code with no network and a read-only repository mount.

    The caller must supply a trusted/pinned container image. Environment
    reconstruction is a separate pipeline and must never silently alter the
    scientific method.
    """
    full_command = docker_command(
        image=image,
        repository=repository,
        command=command,
        limits=limits,
    )
    completed = subprocess.run(
        full_command,
        capture_output=True,
        text=True,
        timeout=limits.timeout_seconds,
        check=False,
    )
    return ExecutionResult(
        command=tuple(full_command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
