from pathlib import Path

from agnxiv.sandbox import SandboxLimits, docker_command


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
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--pids-limit 64" in joined
    assert "--memory 2g" in joined
    assert "--cpus 1.0" in joined
    assert "readonly" in joined
