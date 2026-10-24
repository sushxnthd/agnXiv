from pathlib import Path
from types import SimpleNamespace

import pytest

from agnxiv.sandbox import (
    SandboxError,
    SandboxLimits,
    docker_command,
    is_immutable_image_id,
    prepare_artifact_mounts,
    resolve_local_image_id,
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
    assert "--ipc private" in joined
    assert "--user 65534:65534" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--pids-limit 64" in joined
    assert "--memory 2g" in joined
    assert "--cpus 1.0" in joined
    assert "nodev" in joined
    assert "uid=65534" in joined
    assert "gid=65534" in joined
    assert "readonly" in joined


def test_image_identity_requires_canonical_sha256() -> None:
    assert is_immutable_image_id("sha256:" + "a" * 64)
    assert not is_immutable_image_id("sha256:built")
    assert not is_immutable_image_id("sha256:" + "A" * 64)
    assert not is_immutable_image_id("sha256:" + "a" * 63)
    assert not is_immutable_image_id(" sha256:" + "a" * 64)


def test_docker_inspection_rejects_malformed_content_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "agnxiv.sandbox.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="sha256:not-a-content-id\n",
            stderr="",
        ),
    )
    with pytest.raises(SandboxError, match="non-canonical"):
        resolve_local_image_id("python:3.11-slim")


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


def test_repository_mount_source_rejects_delimiter_injection(tmp_path: Path) -> None:
    unsafe_repo = tmp_path / "unsafe,repo"
    unsafe_repo.mkdir()

    with pytest.raises(ValueError, match="repository path"):
        docker_command(
            image="python:3.11-slim",
            repository=unsafe_repo,
            command=["python", "evaluate.py"],
        )
