from pathlib import Path

from agnxiv.environment import infer_python_environment


def test_infers_requirements_environment(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (tmp_path / "evaluate.py").write_text("print(1)\n", encoding="utf-8")

    spec = infer_python_environment(tmp_path)

    assert "requirements.txt" in spec.dependency_files
    assert ["python", "-m", "pip", "install", "-r", "requirements.txt"] in spec.install_commands
    assert spec.confidence >= 0.8
    assert spec.reconstruction_supported is True


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
    assert spec.reconstruction_supported is False


def test_version_pinned_requirements_are_historically_constrained(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "numpy==2.1.0\nscipy==1.14.1\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_source == "manifest"
    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is True


def test_exact_python_version_changes_historical_base_image(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.10.14\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")

    spec = infer_python_environment(tmp_path)

    assert spec.python_version == "3.10"
    assert spec.base_image == "python:3.10-slim"
    assert any(".python-version" in note for note in spec.notes)


def test_pinned_pep621_dependencies_are_recognized(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "paper"\n'
        'version = "0.1.0"\n'
        'dependencies = ["numpy==1.26.4", "scipy==1.11.4"]\n',
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is True


def test_pinned_setup_cfg_dependencies_are_recognized(tmp_path: Path) -> None:
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = paper\n"
        "[options]\ninstall_requires =\n"
        "    numpy==1.26.4\n"
        "    scipy==1.11.4\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is True


def test_pinned_conda_environment_recovers_python_version(tmp_path: Path) -> None:
    (tmp_path / "environment.yml").write_text(
        "name: paper\n"
        "dependencies:\n"
        "  - python=3.10.14\n"
        "  - numpy=1.26.4\n"
        "  - scipy=1.11.4\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.python_version == "3.10"
    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is False
    assert "Conda" in spec.reconstruction_reason


def test_floating_manifest_prevents_other_manifest_from_looking_fully_pinned(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text("numpy>=1.20\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "paper"\n'
        'version = "0.1.0"\n'
        'dependencies = ["scipy==1.11.4"]\n',
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_precision == "floating"
    assert spec.historical_fidelity == "approximate"


def test_pipfile_lock_is_recorded_as_historical_constraint(tmp_path: Path) -> None:
    (tmp_path / "Pipfile.lock").write_text('{"default": {}}\n', encoding="utf-8")

    spec = infer_python_environment(tmp_path)

    assert "Pipfile.lock" in spec.dependency_files
    assert spec.dependency_source == "lockfile"
    assert spec.dependency_precision == "locked"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is False
    assert "Pipfile.lock" in spec.reconstruction_reason


def test_readme_referenced_nested_conda_is_historically_constrained(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "examples" / "NLU"
    nested.mkdir(parents=True)
    (tmp_path / "README.md").write_text(
        "Follow examples/NLU/ for reproduction.\n",
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='loralib', version='0.1.0')\n",
        encoding="utf-8",
    )
    (nested / "environment.yml").write_text(
        "name: NLU\n"
        "channels:\n"
        "  - pytorch\n"
        "  - defaults\n"
        "dependencies:\n"
        "  - python=3.7.10=h12debd9_4\n"
        "  - numpy=1.20.2=py37h2d18471_0\n"
        "  - pip=21.1.3=py37h06a4308_0\n"
        "  - pip:\n"
        "    - datasets==1.9.0\n",
        encoding="utf-8",
    )

    spec = infer_python_environment(tmp_path)

    assert spec.dependency_source == "manifest"
    assert spec.dependency_precision == "version-pinned"
    assert spec.historical_fidelity == "constrained"
    assert spec.reconstruction_supported is True
    assert "examples/NLU/environment.yml" in spec.dependency_files
