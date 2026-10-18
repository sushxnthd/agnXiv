from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class SandboxError(RuntimeError):
    """A controlled failure while preparing or executing an isolated run."""


@dataclass(frozen=True)
class SandboxLimits:
    memory: str = "4g"
    cpus: float = 2.0
    pids: int = 256
    timeout_seconds: int = 600
    workspace_size: str = "4g"


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    image_id: str
    returncode: int
    stdout: str
    stderr: str


def resolve_local_image_id(image: str) -> str:
    """Resolve a local image reference to the immutable image content ID."""
    if not image.strip():
        raise ValueError("container image is required")

    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxError(f"could not inspect container image: {exc}") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise SandboxError(
            f"container image is not available locally: {image}: {message}"
        )

    image_id = completed.stdout.strip()
    if not image_id.startswith("sha256:"):
        raise SandboxError(
            f"Docker returned a non-content-addressed image ID: {image_id}"
        )
    return image_id


def docker_command(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    limits: SandboxLimits | None = None,
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> list[str]:
    """Build the locked-down Docker command used for research execution."""
    active_limits = limits or SandboxLimits()
    repo = Path(repository).resolve()

    if not repo.is_dir():
        raise ValueError(f"repository path is not a directory: {repo}")
    if not image.strip():
        raise ValueError("container image is required")
    if not command:
        raise ValueError("research command is required")

    base = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(active_limits.pids),
        "--memory",
        active_limits.memory,
        "--cpus",
        str(active_limits.cpus),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=1g",
    ]

    if workspace_mode == "readonly":
        return [
            *base,
            "--mount",
            f"type=bind,src={repo},dst=/workspace,readonly",
            "--workdir",
            "/workspace",
            image,
            *command,
        ]

    shell_command = (
        "cp -a /source/. /workspace/ && "
        "cd /workspace && "
        "exec " + shlex.join(command)
    )
    return [
        *base,
        "--mount",
        f"type=bind,src={repo},dst=/source,readonly",
        "--tmpfs",
        f"/workspace:rw,nosuid,size={active_limits.workspace_size}",
        "--workdir",
        "/workspace",
        image,
        "sh",
        "-lc",
        shell_command,
    ]


def execute_in_docker(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    limits: SandboxLimits | None = None,
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> ExecutionResult:
    """Execute research code with no network and an immutable host source tree."""
    active_limits = limits or SandboxLimits()
    image_id = resolve_local_image_id(image)
    full_command = docker_command(
        image=image_id,
        repository=repository,
        command=command,
        limits=active_limits,
        workspace_mode=workspace_mode,
    )

    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=active_limits.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxError(f"isolated execution failed: {exc}") from exc

    return ExecutionResult(
        command=tuple(full_command),
        image_id=image_id,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
