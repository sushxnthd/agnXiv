from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import threading
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
    output_bytes: int = 16 * 1024 * 1024


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


def prepare_artifact_mounts(
    artifact_paths: list[str | Path] | None,
) -> tuple[ArtifactMount, ...]:
    """Resolve external evidence into deterministic read-only mount locations."""
    mounts: list[ArtifactMount] = []

    for index, value in enumerate(artifact_paths or []):
        path = Path(value).resolve()
        if not path.exists():
            raise ValueError(f"artifact path does not exist: {path}")
        if "," in str(path) or "\n" in str(path):
            raise ValueError("artifact paths may not contain commas or newlines")

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
    repo = Path(repository).resolve()
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
        "--read-only",
        "--user",
        "65534:65534",
        "--env",
        "HOME=/tmp",
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
        "/tmp:rw,noexec,nosuid,nodev,size=1g,uid=65534,gid=65534,mode=1777",
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
            "uid=65534,gid=65534,mode=0755"
        ),
        "--workdir",
        "/workspace",
        image,
        "sh",
        "-lc",
        shell_command,
    ]


def _run_bounded_process(
    command: list[str],
    *,
    timeout_seconds: int,
    output_bytes: int,
) -> tuple[int, bytes, bytes]:
    """Run a child process without allowing unbounded captured output."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if output_bytes <= 0:
        raise ValueError("output_bytes must be positive")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SandboxError(f"isolated execution failed to start: {exc}") from exc

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    lock = threading.Lock()
    output_exceeded = threading.Event()

    def drain(name: str, stream) -> None:
        nonlocal total
        try:
            while True:
                chunk = (
                    stream.read1(64 * 1024)
                    if hasattr(stream, "read1")
                    else stream.read(64 * 1024)
                )
                if not chunk:
                    return
                should_kill = False
                with lock:
                    remaining = output_bytes - total
                    if remaining > 0:
                        accepted = chunk[:remaining]
                        buffers[name].extend(accepted)
                        total += len(accepted)
                    if len(chunk) > max(0, remaining) or total >= output_bytes:
                        output_exceeded.set()
                        should_kill = True
                if should_kill:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    return
        finally:
            try:
                stream.close()
            except OSError:
                pass

    assert process.stdout is not None
    assert process.stderr is not None
    threads = [
        threading.Thread(
            target=drain,
            args=("stdout", process.stdout),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=("stderr", process.stderr),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            process.kill()
        except OSError:
            pass
        process.wait(timeout=10)

    for thread in threads:
        thread.join(timeout=10)
    if any(thread.is_alive() for thread in threads):
        try:
            process.kill()
        except OSError:
            pass
        raise SandboxError("isolated execution output streams did not terminate")

    if timed_out:
        raise SandboxError(
            f"isolated execution exceeded timeout of {timeout_seconds} seconds"
        )
    if output_exceeded.is_set():
        raise SandboxError(
            f"isolated execution exceeded output limit of {output_bytes} bytes"
        )

    return process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"])


def _cleanup_container(cidfile: Path, *, force: bool) -> None:
    """Remove an abnormal Docker container and always remove its cidfile."""
    try:
        container_id = (
            cidfile.read_text(encoding="utf-8", errors="ignore").strip()
            if cidfile.exists()
            else ""
        )
        if force and re.fullmatch(r"[0-9a-f]{12,64}", container_id):
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True,
                timeout=30,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        cidfile.unlink(missing_ok=True)


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

    fd, cidfile_name = tempfile.mkstemp(prefix="agnxiv-cid-", suffix=".txt")
    os.close(fd)
    cidfile = Path(cidfile_name)
    cidfile.unlink(missing_ok=True)
    bounded_command = [
        *full_command[:2],
        "--cidfile",
        str(cidfile),
        *full_command[2:],
    ]

    try:
        returncode, stdout_bytes, stderr_bytes = _run_bounded_process(
            bounded_command,
            timeout_seconds=active_limits.timeout_seconds,
            output_bytes=active_limits.output_bytes,
        )
    except SandboxError:
        _cleanup_container(cidfile, force=True)
        raise
    else:
        _cleanup_container(cidfile, force=False)

    return ExecutionResult(
        command=tuple(full_command),
        image_id=image_id,
        artifact_mounts=mounts,
        returncode=returncode,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )
