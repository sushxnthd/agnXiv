from __future__ import annotations

import re
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
class ArtifactMount:
    host_path: str
    container_path: str


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    image_id: str
    artifact_mounts: tuple[ArtifactMount, ...]
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


def _safe_artifact_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return cleaned or "artifact"


def _validated_mount_source(value: str | Path, *, label: str) -> Path:
    path = Path(value).resolve()
    raw = str(path)
    if "," in raw or "\n" in raw or "\r" in raw:
        raise ValueError(f"{label} path may not contain commas or newlines")
    return path


def prepare_artifact_mounts(
    artifact_paths: list[str | Path] | None,
) -> tuple[ArtifactMount, ...]:
    """Resolve external evidence into deterministic read-only mount locations."""
    mounts: list[ArtifactMount] = []

    for index, value in enumerate(artifact_paths or []):
        path = _validated_mount_source(value, label="artifact")
        if not path.exists():
            raise ValueError(f"artifact path does not exist: {path}")

        target = f"/agnxiv-artifacts/{index:03d}-{_safe_artifact_name(path.name)}"
        mounts.append(
            ArtifactMount(
                host_path=str(path),
                container_path=target,
            )
        )

    return tuple(mounts)


def _artifact_mount_args(mounts: tuple[ArtifactMount, ...]) -> list[str]:
    args: list[str] = []
    for mount in mounts:
        args.extend(
            [
                "--mount",
                (
                    "type=bind,"
                    f"src={mount.host_path},"
                    f"dst={mount.container_path},"
                    "readonly"
                ),
            ]
        )
    return args


def docker_command(
    *,
    image: str,
    repository: str | Path,
    command: list[str],
    artifact_paths: list[str | Path] | None = None,
    limits: SandboxLimits | None = None,
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> list[str]:
    """Build the locked-down Docker command used for research execution."""
    active_limits = limits or SandboxLimits()
    repo = _validated_mount_source(repository, label="repository")
    mounts = prepare_artifact_mounts(artifact_paths)

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
        "--ipc",
        "private",
        "--user",
        "65534:65534",
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
        "/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1770,uid=65534,gid=65534",
        *_artifact_mount_args(mounts),
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
        "find /source -mindepth 1 -maxdepth 1 ! -name .git "
        "-exec cp -R {} /workspace/ \\; && "
        "cd /workspace && "
        "exec " + shlex.join(command)
    )
    return [
        *base,
        "--mount",
        f"type=bind,src={repo},dst=/source,readonly",
        "--tmpfs",
        (
            f"/workspace:rw,nosuid,nodev,size={active_limits.workspace_size},"
            "mode=0770,uid=65534,gid=65534"
        ),
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
    artifact_paths: list[str | Path] | None = None,
    limits: SandboxLimits | None = None,
    workspace_mode: Literal["readonly", "ephemeral-copy"] = "ephemeral-copy",
) -> ExecutionResult:
    """Execute research code with no network and immutable host evidence."""
    active_limits = limits or SandboxLimits()
    mounts = prepare_artifact_mounts(artifact_paths)
    image_id = resolve_local_image_id(image)
    full_command = docker_command(
        image=image_id,
        repository=repository,
        command=command,
        artifact_paths=artifact_paths,
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
        artifact_mounts=mounts,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
