from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class EnvironmentSpec(BaseModel):
    language: str = "python"
    python_version: str = "3.11"
    dependency_files: list[str] = Field(default_factory=list)
    preferred_dependency_file: str | None = None
    environment_scope: list[str] = Field(default_factory=list)
    scope_resolution: Literal["none", "resolved", "ambiguous"] = "none"
    base_image: str = "python:3.11-slim"
    install_commands: list[list[str]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    dependency_source: Literal["none", "manifest", "lockfile", "import_scan"] = "none"
    dependency_precision: Literal[
        "none", "inferred", "floating", "version-pinned", "locked"
    ] = "none"
    historical_fidelity: Literal["unknown", "approximate", "constrained"] = "unknown"
    inferred_packages: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


_IMPORT_PACKAGE_MAP = {
    "cv2": "opencv-python",
    "einops": "einops",
    "hydra": "hydra-core",
    "matplotlib": "matplotlib",
    "mlflow": "mlflow",
    "numpy": "numpy",
    "omegaconf": "omegaconf",
    "pandas": "pandas",
    "PIL": "Pillow",
    "pytorch_lightning": "pytorch-lightning",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "torch": "torch",
    "torchvision": "torchvision",
    "tqdm": "tqdm",
    "yaml": "PyYAML",
}

_EXACT_REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[^\s;\\]+"
)


_SCOPED_MANIFEST_PRIORITY = (
    "requirements.txt",
    "requirement.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "setup.py",
    "setup.cfg",
)


def _scoped_dependency_manifests(
    root: Path,
    scope_paths: list[str],
) -> list[Path]:
    """Find the nearest dependency manifest for each selected workflow source."""
    found: list[Path] = []

    for raw_scope in scope_paths:
        scope = Path(raw_scope)
        if scope.is_absolute() or ".." in scope.parts:
            continue

        candidate = root / scope
        directory = candidate.parent if candidate.suffix or candidate.is_file() else candidate

        while directory != root and root in directory.parents:
            matches = [
                directory / name
                for name in _SCOPED_MANIFEST_PRIORITY
                if (directory / name).is_file()
                and not (directory / name).is_symlink()
            ]
            if matches:
                # Filename priority must not resolve scientifically competing
                # environments.  Preserve every co-located candidate so the
                # caller can abstain on ambiguity.
                found.extend(matches)
                break
            directory = directory.parent

    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        unique.append(path)
    return unique


def _requirements_precision(path: Path) -> Literal["floating", "version-pinned"]:
    package_lines = [
        raw.strip()
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if raw.strip() and not raw.lstrip().startswith("#") and not raw.lstrip().startswith("-")
    ]
    if package_lines and all(_EXACT_REQUIREMENT_RE.match(line) for line in package_lines):
        return "version-pinned"
    return "floating"


def _local_module_names(root: Path) -> set[str]:
    names = {path.stem for path in root.glob("*.py") if path.is_file()}
    names.update(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    return names


def _infer_import_packages(root: Path) -> list[str]:
    local = _local_module_names(root)
    roots: set[str] = set()

    for path in root.rglob("*.py"):
        if path.is_symlink() or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError, UnicodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".", 1)[0])

    third_party = {
        name
        for name in roots
        if name not in sys.stdlib_module_names and name not in local and not name.startswith("_")
    }
    return sorted(
        {
            _IMPORT_PACKAGE_MAP[name]
            for name in third_party
            if name in _IMPORT_PACKAGE_MAP
        },
        key=str.lower,
    )


def infer_python_environment(
    repository: str | Path,
    *,
    scope_paths: list[str] | None = None,
) -> EnvironmentSpec:
    """Infer a conservative Python environment from metadata, workflow scope, and imports."""
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    dependency_files: list[str] = []
    install_commands: list[list[str]] = []
    notes: list[str] = []
    confidence = 0.25
    dependency_source: Literal["none", "manifest", "lockfile", "import_scan"] = "none"
    dependency_precision: Literal[
        "none", "inferred", "floating", "version-pinned", "locked"
    ] = "none"
    historical_fidelity: Literal["unknown", "approximate", "constrained"] = "unknown"
    preferred_dependency_file: str | None = None
    environment_scope = list(dict.fromkeys(scope_paths or []))
    scope_resolution: Literal["none", "resolved", "ambiguous"] = "none"

    scoped_manifests = _scoped_dependency_manifests(root, environment_scope)
    if len(scoped_manifests) == 1:
        scope_resolution = "resolved"
        scoped = scoped_manifests[0]
        preferred_dependency_file = scoped.relative_to(root).as_posix()
        dependency_files.append(preferred_dependency_file)
        notes.append(
            "Workflow-scoped dependency manifest selected from the nearest "
            f"documented command directory: {preferred_dependency_file}"
        )
        if scoped.name in {"requirements.txt", "requirement.txt"}:
            install_commands.append(
                [
                    "python",
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    preferred_dependency_file,
                ]
            )
            confidence = max(confidence, 0.86)
            dependency_source = "manifest"
            dependency_precision = _requirements_precision(scoped)
            historical_fidelity = (
                "constrained"
                if dependency_precision == "version-pinned"
                else "approximate"
            )
        elif scoped.name in {"environment.yml", "environment.yaml"}:
            confidence = max(confidence, 0.86)
            dependency_source = "manifest"
            dependency_precision = "floating"
            historical_fidelity = "approximate"
            notes.append(
                "Scoped Conda environment detected; a Conda-capable builder is required."
            )
        elif scoped.name in {"poetry.lock", "uv.lock"}:
            confidence = max(confidence, 0.9)
            dependency_source = "lockfile"
            dependency_precision = "locked"
            historical_fidelity = "constrained"
        else:
            confidence = max(confidence, 0.72)
            dependency_source = "manifest"
            dependency_precision = "floating"
            historical_fidelity = "approximate"
    elif len(scoped_manifests) > 1:
        scope_resolution = "ambiguous"
        dependency_files.extend(
            path.relative_to(root).as_posix()
            for path in scoped_manifests
        )
        notes.append(
            "Multiple workflow-scoped dependency manifests were discovered; "
            "AgnXiv will not choose among them automatically."
        )
        confidence = max(confidence, 0.55)

    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"
    poetry_lock = root / "poetry.lock"
    uv_lock = root / "uv.lock"
    environment_yml = root / "environment.yml"
    environment_yaml = root / "environment.yaml"

    # Once workflow scope resolves (or reveals a conflict), root metadata is
    # not the executed environment and must not overwrite its precision,
    # fidelity, or install commands.
    if requirements.exists() and scope_resolution == "none":
        dependency_files.append("requirements.txt")
        install_commands.append(["python", "-m", "pip", "install", "-r", "requirements.txt"])
        confidence = max(confidence, 0.8)
        dependency_source = "manifest"
        dependency_precision = _requirements_precision(requirements)
        historical_fidelity = (
            "constrained"
            if dependency_precision == "version-pinned"
            else "approximate"
        )

    if pyproject.exists() and scope_resolution == "none":
        dependency_files.append("pyproject.toml")
        install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.75)
        dependency_source = "manifest"
        if dependency_precision == "none":
            dependency_precision = "floating"
            historical_fidelity = "approximate"

    if setup_py.exists() and scope_resolution == "none":
        dependency_files.append("setup.py")
        if not pyproject.exists():
            install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.65)
        dependency_source = "manifest"
        if dependency_precision == "none":
            dependency_precision = "floating"
            historical_fidelity = "approximate"

    if setup_cfg.exists() and scope_resolution == "none":
        dependency_files.append("setup.cfg")
        confidence = max(confidence, 0.55)
        dependency_source = "manifest"
        if dependency_precision == "none":
            dependency_precision = "floating"
            historical_fidelity = "approximate"

    if poetry_lock.exists() and scope_resolution == "none":
        dependency_files.append("poetry.lock")
        notes.append("Poetry lockfile detected; prefer the exact locked dependency set.")
        confidence = max(confidence, 0.85)
        dependency_source = "lockfile"
        dependency_precision = "locked"
        historical_fidelity = "constrained"

    if uv_lock.exists() and scope_resolution == "none":
        dependency_files.append("uv.lock")
        notes.append("uv lockfile detected; prefer the exact locked dependency set.")
        confidence = max(confidence, 0.9)
        dependency_source = "lockfile"
        dependency_precision = "locked"
        historical_fidelity = "constrained"

    conda_file = environment_yml if environment_yml.exists() else environment_yaml
    if conda_file.exists() and scope_resolution == "none":
        dependency_files.append(conda_file.name)
        notes.append("Conda environment detected; a Conda-capable builder is required.")
        confidence = max(confidence, 0.8)
        dependency_source = "manifest"
        if dependency_precision == "none":
            dependency_precision = "floating"
            historical_fidelity = "approximate"

    python_files = list(root.rglob("*.py"))
    inferred_packages = _infer_import_packages(root) if python_files else []
    if python_files and not dependency_files:
        notes.append("Python source detected but no dependency manifest was found.")
        if inferred_packages:
            notes.append(
                "Third-party dependencies were inferred statically from imports; "
                "package versions remain unknown."
            )
            dependency_source = "import_scan"
            dependency_precision = "inferred"
            historical_fidelity = "unknown"
            confidence = max(confidence, 0.62)
        else:
            confidence = max(confidence, 0.4)

    return EnvironmentSpec(
        dependency_files=list(dict.fromkeys(dependency_files)),
        preferred_dependency_file=preferred_dependency_file,
        environment_scope=environment_scope,
        scope_resolution=scope_resolution,
        install_commands=install_commands,
        confidence=confidence,
        dependency_source=dependency_source,
        dependency_precision=dependency_precision,
        historical_fidelity=historical_fidelity,
        inferred_packages=inferred_packages,
        notes=notes,
    )
