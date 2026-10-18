from pathlib import Path

from agnxiv.planner import discover_commands


def test_prefers_reproduction_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "reproduce.py").write_text("print('accuracy: 91.4%')\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")

    commands = discover_commands(tmp_path)

    assert commands
    assert commands[0].command == ["python", "reproduce.py"]
