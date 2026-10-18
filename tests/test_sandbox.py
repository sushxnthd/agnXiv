import sys
from pathlib import Path

import pytest

from agnxiv.sandbox import (
    SandboxError,
    SandboxLimits,
    _run_bounded_process,
    docker_command,
    prepare_artifact_mounts,
)


def test_docker_command_is_locked_down(tmp_path: Path) -> None:
    command = docker_command(
        image="python:3.11-slim",
        repository=tmp_path,
        command=["python", "evaluate.py"],
        limits=SandboxLimits(memory="2g", cpus=1.0, pids=64),
    )

    joined = " ".join(command)
    assert "--network none" in joined
    assert "--read-only" in command
    assert "--user" in command
    assert "65534:65534" in command
    assert "HOME=/tmp" in command
    assert "nodev" in joined
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--pids-limit 64" in joined
    assert "--memory 2g" in joined
    assert "--cpus 1.0" in joined
    assert "readonly" in joined


def test_external_artifacts_get_deterministic_readonly_mounts(tmp_path: Path) -> None:
    artifact = tmp_path / "dataset.csv"
    artifact.write_text("x,y\n1,2\n", encoding="utf-8")

    mounts = prepare_artifact_mounts([artifact])
    assert len(mounts) == 1
    assert mounts[0].container_path == "/agnxiv-artifacts/000-dataset.csv"

    command = docker_command(
        image="python:3.11-slim",
        repository=tmp_path,
        command=["python", "evaluate.py"],
        artifact_paths=[artifact],
    )
    joined = " ".join(command)
    assert str(artifact.resolve()) in joined
    assert "dst=/agnxiv-artifacts/000-dataset.csv,readonly" in joined

def test_workspace_copy_excludes_git_metadata(tmp_path: Path) -> None:
    command = docker_command(
        image="python:3.11-slim",
        repository=tmp_path,
        command=["python", "evaluate.py"],
    )
    shell_command = command[-1]
    assert "! -name .git" in shell_command
    assert "cp -R /source/. /workspace/" not in shell_command
    assert "--network" in command


def test_bounded_process_accepts_small_output() -> None:
    returncode, stdout, stderr = _run_bounded_process(
        [sys.executable, "-c", "print('bounded-ok')"],
        timeout_seconds=5,
        output_bytes=4096,
    )
    assert returncode == 0
    assert b"bounded-ok" in stdout
    assert stderr == b""


def test_bounded_process_kills_output_flood() -> None:
    with pytest.raises(SandboxError, match="output limit"):
        _run_bounded_process(
            [sys.executable, "-c", "print('x' * 1000000)"],
            timeout_seconds=5,
            output_bytes=4096,
        )


def test_bounded_process_kills_timeout() -> None:
    with pytest.raises(SandboxError, match="exceeded timeout"):
        _run_bounded_process(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout_seconds=1,
            output_bytes=4096,
        )
