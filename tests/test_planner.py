from pathlib import Path

import pytest

from agnxiv.planner import discover_commands


def test_prefers_reproduction_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "reproduce.py").write_text("print('accuracy: 91.4%')\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")

    commands = discover_commands(tmp_path)

    assert commands
    assert commands[0].command == ["python", "reproduce.py"]


def test_does_not_discover_symlinked_entrypoint(tmp_path: Path) -> None:
    outside = tmp_path.parent / "agnxiv-outside-reproduce.py"
    outside.write_text("print('external')\n", encoding="utf-8")
    link = tmp_path / "reproduce.py"

    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    assert discover_commands(tmp_path) == []
