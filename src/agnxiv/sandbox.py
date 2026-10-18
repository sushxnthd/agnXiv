from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


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
    returncode: int
    stdout: str
    stderr: str


def docker_command(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    limits: SandboxLimits = SandboxLimits(),
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> list[str]:
    """Build the locked-down Docker command used for research execution."""
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
        str(limits.pids),
        "--memory",
        limits.memory,
        "--cpus",
        str(limits.cpus),
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

    # The fingerprinted host repository remains immutable. A disposable copy is
    # made inside container tmpfs so normal research scripts may create outputs,
    # caches or checkpoints without mutating the verified source tree.
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
        f"/workspace:rw,nosuid,size={limits.workspace_size}",
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
    limits: SandboxLimits = SandboxLimits(),
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> ExecutionResult:
    """Execute research code with no network and an immutable host source tree.

    Images must already exist locally; pull-never prevents Docker from silently
    fetching an unpinned image at verification time.
    """
    full_command = docker_command(
        image=image,
        repository=repository,
        command=command,
        limits=limits,
        workspace_mode=workspace_mode,
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
