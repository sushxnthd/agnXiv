from __future__ import annotations

import ast
import configparser
import re
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class EnvironmentSpec(BaseModel):
    language: str = "python"
    python_version: str = "3.11"
    dependency_files: list[str] = Field(default_factory=list)
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
    reconstruction_supported: bool = False
    reconstruction_reason: str = "environment has not been matched to an available builder"


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
_EXACT_PYTHON_RE = re.compile(r"^(?:python-)?(?P<version>3\.\d+)(?:\.\d+)?$")
_CONDA_PYTHON_RE = re.compile(
    r"^\s*-\s*python\s*=\s*(?P<version>3\.\d+)(?:\.\d+)?(?:\s|$)"
)


def _exact_requirement_set(requirements: list[str]) -> bool:
    cleaned = [
        item.strip()
        for item in requirements
        if item.strip() and not item.lstrip().startswith("#")
    ]
    return bool(cleaned) and all(_EXACT_REQUIREMENT_RE.match(item) for item in cleaned)


def _pyproject_precision(path: Path) -> Literal["floating", "version-pinned"]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return "floating"

    project = payload.get("project")
    if isinstance(project, dict):
        dependencies = project.get("dependencies")
        if isinstance(dependencies, list) and dependencies:
            values = [item for item in dependencies if isinstance(item, str)]
            if len(values) == len(dependencies) and _exact_requirement_set(values):
                return "version-pinned"

    poetry = payload.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        dependencies = poetry.get("dependencies")
        if isinstance(dependencies, dict):
            values = []
            for name, constraint in dependencies.items():
                if str(name).lower() == "python":
                    continue
                if not isinstance(constraint, str) or not re.fullmatch(
                    r"\d+(?:\.\d+){1,3}", constraint
                ):
                    return "floating"
                values.append(f"{name}=={constraint}")
            if values and _exact_requirement_set(values):
                return "version-pinned"
    return "floating"


def _setup_cfg_precision(path: Path) -> Literal["floating", "version-pinned"]:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return "floating"
    raw = parser.get("options", "install_requires", fallback="")
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    return "version-pinned" if _exact_requirement_set(values) else "floating"


def _conda_precision(path: Path) -> Literal["floating", "version-pinned"]:
    """Conservatively recognize only fully pinned simple Conda/Pip dependency rows."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return "floating"

    in_dependencies = False
    saw_dependency = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw == stripped and stripped == "dependencies:":
            in_dependencies = True
            continue
        if raw == stripped and stripped.endswith(":") and stripped != "dependencies:":
            if in_dependencies:
                break
            continue
        if not in_dependencies:
            continue
        if stripped == "- pip:":
            continue
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        saw_dependency = True
        if "==" in value:
            if not _EXACT_REQUIREMENT_RE.match(value):
                return "floating"
        elif not re.fullmatch(
            r"[A-Za-z0-9_.-]+=\d+(?:\.\d+){0,3}(?:=[A-Za-z0-9_.-]+)?",
            value,
        ):
            return "floating"
    return "version-pinned" if saw_dependency else "floating"


def _infer_exact_python_version(
    root: Path,
    conda_file: Path | None,
) -> tuple[str | None, str | None]:
    for filename in (".python-version", "runtime.txt"):
        path = root / filename
        if not path.is_file() or path.is_symlink():
            continue
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        match = _EXACT_PYTHON_RE.fullmatch(value)
        if match:
            return match.group("version"), filename

    if conda_file is not None and conda_file.is_file() and not conda_file.is_symlink():
        for raw in conda_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = _CONDA_PYTHON_RE.match(raw)
            if match:
                return match.group("version"), conda_file.name
    return None, None


def _merge_manifest_precision(
    current: Literal["none", "inferred", "floating", "version-pinned", "locked"],
    new: Literal["floating", "version-pinned"],
) -> Literal["none", "inferred", "floating", "version-pinned", "locked"]:
    if current == "none":
        return new
    if current == "locked":
        return current
    if current == "inferred":
        return new
    if current == "floating" or new == "floating":
        return "floating"
    return "version-pinned"


def _requirements_precision(path: Path) -> Literal["floating", "version-pinned"]:
    package_lines = [
        raw.strip()
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if raw.strip()
        and not raw.lstrip().startswith("#")
        and not raw.lstrip().startswith("-")
    ]
    return "version-pinned" if _exact_requirement_set(package_lines) else "floating"


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


def infer_python_environment(repository: str | Path) -> EnvironmentSpec:
    """Infer a conservative Python environment from repository metadata and imports."""
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
    python_version = "3.11"

    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"
    poetry_lock = root / "poetry.lock"
    uv_lock = root / "uv.lock"
    pipfile_lock = root / "Pipfile.lock"
    environment_yml = root / "environment.yml"
    environment_yaml = root / "environment.yaml"

    if requirements.exists():
        dependency_files.append("requirements.txt")
        install_commands.append(["python", "-m", "pip", "install", "-r", "requirements.txt"])
        confidence = max(confidence, 0.8)
        dependency_source = "manifest"
        dependency_precision = _merge_manifest_precision(
            dependency_precision,
            _requirements_precision(requirements),
        )
        historical_fidelity = (
            "constrained"
            if dependency_precision == "version-pinned"
            else "approximate"
        )

    if pyproject.exists():
        dependency_files.append("pyproject.toml")
        install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.75)
        dependency_source = "manifest"
        pyproject_precision = _pyproject_precision(pyproject)
        dependency_precision = _merge_manifest_precision(
            dependency_precision,
            pyproject_precision,
        )
        historical_fidelity = (
            "constrained"
            if dependency_precision == "version-pinned"
            else "approximate"
        )

    if setup_py.exists():
        dependency_files.append("setup.py")
        if not pyproject.exists():
            install_commands.append(["python", "-m", "pip", "install", "."])
        confidence = max(confidence, 0.65)
        dependency_source = "manifest"
        dependency_precision = _merge_manifest_precision(
            dependency_precision,
            "floating",
        )
        historical_fidelity = "approximate"

    if setup_cfg.exists():
        dependency_files.append("setup.cfg")
        confidence = max(confidence, 0.55)
        dependency_source = "manifest"
        setup_precision = _setup_cfg_precision(setup_cfg)
        dependency_precision = _merge_manifest_precision(
            dependency_precision,
            setup_precision,
        )
        historical_fidelity = (
            "constrained"
            if dependency_precision == "version-pinned"
            else "approximate"
        )

    if poetry_lock.exists():
        dependency_files.append("poetry.lock")
        notes.append("Poetry lockfile detected; prefer the exact locked dependency set.")
        confidence = max(confidence, 0.85)
        dependency_source = "lockfile"
        dependency_precision = "locked"
        historical_fidelity = "constrained"

    if uv_lock.exists():
        dependency_files.append("uv.lock")
        notes.append("uv lockfile detected; prefer the exact locked dependency set.")
        confidence = max(confidence, 0.9)
        dependency_source = "lockfile"
        dependency_precision = "locked"
        historical_fidelity = "constrained"

    if pipfile_lock.exists():
        dependency_files.append("Pipfile.lock")
        notes.append("Pipfile.lock detected; prefer the exact locked dependency set.")
        confidence = max(confidence, 0.85)
        dependency_source = "lockfile"
        dependency_precision = "locked"
        historical_fidelity = "constrained"

    conda_file = environment_yml if environment_yml.exists() else environment_yaml
    if conda_file.exists():
        dependency_files.append(conda_file.name)
        notes.append("Conda environment detected; a Conda-capable builder is required.")
        confidence = max(confidence, 0.8)
        dependency_source = "manifest"
        conda_precision = _conda_precision(conda_file)
        dependency_precision = _merge_manifest_precision(
            dependency_precision,
            conda_precision,
        )
        historical_fidelity = (
            "constrained"
            if dependency_precision == "version-pinned"
            else "approximate"
        )

    exact_python, python_source = _infer_exact_python_version(
        root,
        conda_file if conda_file.exists() else None,
    )
    if exact_python is not None:
        python_version = exact_python
        notes.append(
            f"Exact Python {python_version} inferred from {python_source}; "
            "hosted execution may abstain if that runtime is outside the supported set."
        )

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

    from .build import plan_python_environment

    build_plan = plan_python_environment(
        root,
        base_image=f"python:{python_version}-slim",
    )
    if build_plan.builder == "conda-micromamba-metadata":
        if build_plan.dependency_file and build_plan.dependency_file not in dependency_files:
            dependency_files.append(build_plan.dependency_file)
        dependency_source = "manifest"
        dependency_precision = "version-pinned"
        historical_fidelity = "constrained"
        confidence = max(confidence, 0.9)
        notes.append(
            "A README-referenced, fully pinned Conda environment can be "
            "replayed through the metadata-only micromamba builder."
        )
    unsupported_exact_sources = [
        name
        for name in ("poetry.lock", "uv.lock", "Pipfile.lock")
        if (root / name).exists()
    ]
    if build_plan.builder == "conda-micromamba-metadata":
        reconstruction_supported = build_plan.safe_manifest_only
        reconstruction_reason = (
            "The active metadata-only micromamba builder can replay the "
            "fully pinned Conda environment without exposing research source."
            if build_plan.safe_manifest_only
            else "; ".join(build_plan.rejected_reasons)
        )
    elif conda_file.exists():
        reconstruction_supported = False
        reconstruction_reason = (
            "Conda metadata was detected but the hosted dependency builder "
            "could not safely replay this environment."
        )
    elif unsupported_exact_sources:
        reconstruction_supported = False
        reconstruction_reason = (
            "Exact lock metadata is present but is not replayed by the active "
            "hosted dependency builder: " + ", ".join(unsupported_exact_sources)
        )
    elif dependency_source == "import_scan":
        reconstruction_supported = False
        reconstruction_reason = (
            "Dependencies were inferred from imports but exact install metadata "
            "is unavailable."
        )
    elif build_plan.safe_manifest_only:
        reconstruction_supported = True
        reconstruction_reason = (
            "The active dependency-only builder can reconstruct the detected "
            f"metadata via {build_plan.builder}."
        )
    else:
        reconstruction_supported = False
        reconstruction_reason = "; ".join(build_plan.rejected_reasons) or (
            "The detected dependency metadata is unsupported by the active builder."
        )

    return EnvironmentSpec(
        python_version=python_version,
        base_image=f"python:{python_version}-slim",
        dependency_files=dependency_files,
        install_commands=install_commands,
        confidence=confidence,
        dependency_source=dependency_source,
        dependency_precision=dependency_precision,
        historical_fidelity=historical_fidelity,
        inferred_packages=inferred_packages,
        notes=notes,
        reconstruction_supported=reconstruction_supported,
        reconstruction_reason=reconstruction_reason,
    )
