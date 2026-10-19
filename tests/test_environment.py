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


def test_prefers_nearest_workflow_scoped_requirements(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n", encoding="utf-8")
    scoped = tmp_path / "examples" / "NLG"
    (scoped / "eval").mkdir(parents=True)
    (scoped / "requirement.txt").write_text(
        "torch==1.7.1\ntransformers==3.3.1\n",
        encoding="utf-8",
    )
    (scoped / "eval" / "eval.py").write_text("print('ok')\n", encoding="utf-8")

    spec = infer_python_environment(
        tmp_path,
        scope_paths=["examples/NLG/eval/eval.py"],
    )

    assert spec.scope_resolution == "resolved"
    assert spec.preferred_dependency_file == "examples/NLG/requirement.txt"
    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert [
        "python",
        "-m",
        "pip",
        "install",
        "-r",
        "examples/NLG/requirement.txt",
    ] in spec.install_commands


def test_abstains_from_choosing_between_multiple_scoped_environments(tmp_path: Path) -> None:
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
        (directory / "eval.py").write_text("print('ok')\n", encoding="utf-8")

    spec = infer_python_environment(
        tmp_path,
        scope_paths=["a/eval.py", "b/eval.py"],
    )

    assert spec.scope_resolution == "ambiguous"
    assert spec.preferred_dependency_file is None
    assert sorted(spec.dependency_files) == [
        "a/requirements.txt",
        "b/requirements.txt",
    ]
