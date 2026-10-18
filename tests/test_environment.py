from pathlib import Path

from agnxiv.environment import infer_python_environment


def test_infers_requirements_environment(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("print(1)\n", encoding="utf-8")

    spec = infer_python_environment(tmp_path)

    assert "requirements.txt" in spec.dependency_files
    assert ["python", "-m", "pip", "install", "-r", "requirements.txt"] in spec.install_commands
    assert spec.confidence >= 0.8
