from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class EnvironmentSpec(BaseModel):
    language: str = "python"
    python_version: str = "3.11"
    dependency_files: list[str] = Field(default_factory=list)
    base_image: str = "python:3.11-slim"
    install_commands: list[list[str]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


def infer_python_environment(repository: str | Path) -> EnvironmentSpec:
    """Infer a conservative Python environment from repository metadata."""
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    dependency_files: list[str] = []
    install_commands: list[list[str]] = []
    notes: list[str] = []
    confidence = 0.25

    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"
    poetry_lock = root / "poetry.lock"
    uv_lock = root / "uv.lock"
    environment_yml = root / "environment.yml"
    environment_yaml = root / "environment.yaml"

    if requirements.exists():
        dependency_files.append("requirements.txt")
        install_commands.append(["python", "-m", "pip", "install", "-r", "requirements.txt"])
        confidence = max(confidence, 0.8)

    if pyproject.exists():
        dependency_files.append("pyproject.toml")
        install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.75)

    if setup_py.exists():
        dependency_files.append("setup.py")
        if not pyproject.exists():
            install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.65)

    if setup_cfg.exists():
        dependency_files.append("setup.cfg")
        confidence = max(confidence, 0.55)

    if poetry_lock.exists():
        dependency_files.append("poetry.lock")
        notes.append("Poetry lockfile detected; prefer the exact locked environment.")
        confidence = max(confidence, 0.85)

    if uv_lock.exists():
        dependency_files.append("uv.lock")
        notes.append("uv lockfile detected; prefer the exact locked environment.")
        confidence = max(confidence, 0.9)

    conda_file = environment_yml if environment_yml.exists() else environment_yaml
    if conda_file.exists():
        dependency_files.append(conda_file.name)
        notes.append("Conda environment detected; a Conda-capable builder is required.")
        confidence = max(confidence, 0.8)

    python_files = list(root.rglob("*.py"))
    if python_files and not dependency_files:
        notes.append("Python source detected but no dependency manifest was found.")
        confidence = max(confidence, 0.4)

    return EnvironmentSpec(
        dependency_files=dependency_files,
        install_commands=install_commands,
        confidence=confidence,
        notes=notes,
    )
