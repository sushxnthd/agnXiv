from pathlib import Path

from agnxiv.environment import infer_python_environment


def test_infers_requirements_environment(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("print(1)\n", encoding="utf-8")

    spec = infer_python_environment(tmp_path)

    assert "requirements.txt" in spec.dependency_files
    assert ["python", "-m", "pip", "install", "-r", "requirements.txt"] in spec.install_commands
    assert spec.confidence >= 0.8


def test_infers_packages_from_imports_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "model.py").write_text(
        "import torch\nimport numpy as np\nfrom PIL import Image\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_source == "import_scan"
    assert spec.dependency_precision == "inferred"
    assert spec.historical_fidelity == "unknown"
    assert spec.confidence >= 0.6
    assert {"torch", "numpy", "Pillow"}.issubset(set(spec.inferred_packages))


def test_version_pinned_requirements_are_historically_constrained(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "numpy==2.1.0\nscipy==1.14.1\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_source == "manifest"
    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
