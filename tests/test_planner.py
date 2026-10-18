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


def test_discovers_markdown_blockquote_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "> python train.py --dataset data --epochs 10\n",
        encoding="utf-8",
    )

    commands = discover_commands(tmp_path)

    assert any(
        candidate.command == [
            "python",
            "train.py",
            "--dataset",
            "data",
            "--epochs",
            "10",
        ]
        for candidate in commands
    )


def test_discovers_backslash_continued_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "python main.py experiment=supervised \\\n"
        "    experiment.model=saint \\\n"
        "    data=bank_sup\n",
        encoding="utf-8",
    )

    commands = discover_commands(tmp_path)

    assert any(
        candidate.command == [
            "python",
            "main.py",
            "experiment=supervised",
            "experiment.model=saint",
            "data=bank_sup",
        ]
        for candidate in commands
    )


def test_discovers_documented_bash_experiment_script(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "bash ./scripts/ECL_script/Koopa.sh\n",
        encoding="utf-8",
    )

    commands = discover_commands(tmp_path)

    assert any(
        candidate.command == ["bash", "./scripts/ECL_script/Koopa.sh"]
        and candidate.score >= 0.88
        for candidate in commands
    )
