from __future__ import annotations

import configparser
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .provenance import sha256_file
from .sandbox import SandboxError, resolve_local_image_id


class EnvironmentBuildError(RuntimeError):
    """A controlled failure while constructing a research runtime."""


class BuildPlan(BaseModel):
    builder: str = "python-requirements"
    base_image: str
    dependency_file: str | None
    dependency_sha256: str | None
    dependency_precision: Literal[
        "base-only",
        "floating",
        "version-pinned",
        "hash-pinned",
    ]
    dockerfile: str
    network_required: bool
    safe_manifest_only: bool
    rejected_reasons: list[str] = Field(default_factory=list)
    generated_requirements: list[str] = Field(default_factory=list)

    @property
    def plan_id(self) -> str:
        payload = "\n".join(
            [
                self.builder,
                self.base_image,
                self.dependency_file or "",
                self.dependency_sha256 or "",
                self.dependency_precision,
                self.dockerfile,
                "\n".join(self.generated_requirements),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BuildResult(BaseModel):
    plan: BuildPlan
    image_ref: str
    image_id: str
    base_image_id: str
    stdout_sha256: str
    stderr_sha256: str


_MAX_DEPENDENCY_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_REQUIREMENT_LINES = 10_000
_MAX_REQUIREMENT_LINE_CHARS = 8192
_MAX_BUILD_OUTPUT_BYTES = 8 * 1024 * 1024


_MICROMAMBA_VERSION = "2.9.0-0"
_MICROMAMBA_URL = (
    "https://github.com/mamba-org/micromamba-releases/releases/download/"
    f"{_MICROMAMBA_VERSION}/micromamba-linux-64"
)
_MICROMAMBA_SHA256 = "366cd9cd8be14df1ab8ed50352a82111082a36686b2d389fdb79a92c3fafb3e3"
_TRUSTED_CONDA_CHANNELS = {"defaults", "conda-forge", "pytorch", "nvidia"}


def _read_dependency_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise EnvironmentBuildError(
            f"dependency metadata must be a regular non-symlink file: {path.name}"
        )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise EnvironmentBuildError(
            f"dependency metadata could not be inspected: {path.name}"
        ) from exc
    if size > _MAX_DEPENDENCY_MANIFEST_BYTES:
        raise EnvironmentBuildError(
            f"dependency metadata exceeds {_MAX_DEPENDENCY_MANIFEST_BYTES} byte limit: "
            f"{path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentBuildError(
            f"dependency metadata could not be read safely: {path.name}"
        ) from exc
    lines = text.splitlines()
    if len(lines) > _MAX_REQUIREMENT_LINES:
        raise EnvironmentBuildError(
            f"dependency metadata exceeds {_MAX_REQUIREMENT_LINES} line limit: {path.name}"
        )
    if any(len(line) > _MAX_REQUIREMENT_LINE_CHARS for line in lines):
        raise EnvironmentBuildError(
            f"dependency metadata contains an oversized line: {path.name}"
        )
    return text


_UNSAFE_REQUIREMENT_MARKERS = (
    "-e ",
    "--editable",
    "git+",
    "hg+",
    "svn+",
    "bzr+",
    "file:",
    "../",
    "./",
    "http://",
    "https://",
    "--index-url",
    "--extra-index-url",
    "--find-links",
    "--trusted-host",
)

_EXACT_REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[^\s;\\]+"
)


def _active_requirement_lines(path: Path) -> list[str]:
    return [
        raw.strip()
        for raw in _read_dependency_text(path).splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]


def classify_requirement_lines(
    lines: list[str],
) -> Literal["floating", "version-pinned", "hash-pinned"]:
    active = [
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    package_lines = [
        line
        for line in active
        if not line.startswith("-") and not line.startswith("\\")
    ]
    if not package_lines:
        return "floating"
    if not all(_EXACT_REQUIREMENT_RE.match(line) for line in package_lines):
        return "floating"
    has_hashes = any("--hash=sha256:" in line for line in active)
    return "hash-pinned" if has_hashes else "version-pinned"


def audit_requirement_lines(lines: list[str]) -> list[str]:
    reasons: list[str] = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        for marker in _UNSAFE_REQUIREMENT_MARKERS:
            if marker in lower:
                reasons.append(
                    f"line {line_number}: unsupported dependency source or option: {marker}"
                )
                break
    return reasons



def _readme_text(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "readme.md"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return ""
    return ""


def discover_referenced_nested_conda(root: Path) -> Path | None:
    """Return one README-referenced nested Conda manifest, otherwise abstain."""
    candidates: list[Path] = []
    for name in ("environment.yml", "environment.yaml"):
        for path in root.rglob(name):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            if len(relative.parts) > 4 or len(relative.parts) < 2:
                continue
            candidates.append(path)
    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    relative_parent = candidate.parent.relative_to(root).as_posix().rstrip("/") + "/"
    readme = _readme_text(root).replace("\\", "/")
    if relative_parent.lower() not in readme.lower():
        return None
    return candidate


def _audit_conda_environment(path: Path) -> list[str]:
    """Accept only a deliberately small, line-oriented Conda YAML subset."""
    text = _read_dependency_text(path)
    reasons: list[str] = []
    in_channels = False
    in_dependencies = False
    pip_block_indent: int | None = None
    saw_channels = False
    saw_dependencies = False

    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))

        if indent == 0:
            in_channels = False
            in_dependencies = False
            pip_block_indent = None
            if stripped.startswith("name:"):
                value = stripped.partition(":")[2].strip()
                if not value or any(char in value for char in "[]{}&*!|>@"):
                    reasons.append(f"line {number}: unsafe Conda environment name")
                continue
            if stripped == "channels:":
                saw_channels = True
                in_channels = True
                continue
            if stripped == "dependencies:":
                saw_dependencies = True
                in_dependencies = True
                continue
            if stripped.startswith("prefix:"):
                # Machine-local prefixes are stripped from the generated file.
                continue
            reasons.append(
                f"line {number}: unsupported top-level Conda metadata"
            )
            continue

        if in_channels:
            if indent < 2 or not stripped.startswith("- "):
                reasons.append(f"line {number}: unsupported Conda channel syntax")
                continue
            channel = stripped[2:].strip()
            if channel not in _TRUSTED_CONDA_CHANNELS:
                reasons.append(
                    f"line {number}: untrusted Conda channel: {channel}"
                )
            continue

        if in_dependencies:
            if not stripped.startswith("- "):
                reasons.append(
                    f"line {number}: unsupported Conda dependency syntax"
                )
                continue
            value = stripped[2:].strip()
            lower = value.lower()

            if value == "pip:":
                if indent < 2:
                    reasons.append(f"line {number}: malformed pip dependency block")
                else:
                    pip_block_indent = indent
                continue

            if pip_block_indent is not None and indent > pip_block_indent:
                if any(marker in lower for marker in _UNSAFE_REQUIREMENT_MARKERS):
                    reasons.append(
                        f"line {number}: unsupported Pip dependency source"
                    )
                elif not _EXACT_REQUIREMENT_RE.fullmatch(value):
                    reasons.append(
                        f"line {number}: Pip dependency is not exactly pinned"
                    )
                continue

            pip_block_indent = None
            if any(marker in lower for marker in _UNSAFE_REQUIREMENT_MARKERS):
                reasons.append(
                    f"line {number}: unsupported Conda dependency source"
                )
                continue
            if not re.fullmatch(
                r"[A-Za-z0-9_.-]+=\d+(?:\.\d+){0,4}(?:[A-Za-z0-9_.+-]*)"
                r"(?:=[A-Za-z0-9_.+-]+)?",
                value,
            ):
                reasons.append(
                    f"line {number}: Conda dependency is not exactly pinned"
                )
            continue

        reasons.append(f"line {number}: unsupported Conda YAML structure")

    if not saw_dependencies:
        reasons.append("Conda environment is missing a block dependencies section")
    if not saw_channels:
        reasons.append("Conda environment is missing a block channels section")
    return reasons


def _conda_environment_plan(path: Path, *, root: Path, base_image: str) -> BuildPlan:
    rejected = _audit_conda_environment(path)
    relative = path.relative_to(root).as_posix()
    sanitized = [
        line
        for line in _read_dependency_text(path).splitlines()
        if not line.startswith("prefix:")
    ]
    generated = sanitized
    dockerfile = (
        f"FROM {base_image}\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 "
        "MAMBA_ROOT_PREFIX=/opt/micromamba\n"
        "RUN python -c \"import hashlib,pathlib,urllib.request; "
        f"u={_MICROMAMBA_URL!r}; e={_MICROMAMBA_SHA256!r}; "
        "d=urllib.request.urlopen(u,timeout=60).read(33554432); "
        "h=hashlib.sha256(d).hexdigest(); "
        "h==e or (_ for _ in ()).throw(SystemExit('micromamba digest mismatch')); "
        "p=pathlib.Path('/usr/local/bin/micromamba'); p.write_bytes(d); "
        "p.chmod(0o755)\"\n"
        "COPY agnxiv-generated-environment.yml /tmp/environment.yml\n"
        "RUN micromamba create -y -p /opt/agnxiv-env -f /tmp/environment.yml "
        "&& micromamba clean --all --yes\n"
        "ENV PATH=/opt/agnxiv-env/bin:$PATH\n"
        "WORKDIR /workspace\n"
    )
    return BuildPlan(
        builder="conda-micromamba-metadata",
        base_image=base_image,
        dependency_file=relative,
        dependency_sha256=sha256_file(path),
        dependency_precision="version-pinned",
        dockerfile=dockerfile,
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
        generated_requirements=generated,
    )


def _pyproject_runtime_requirements(
    path: Path,
) -> tuple[list[str] | None, list[str]]:
    try:
        payload = tomllib.loads(_read_dependency_text(path))
    except (EnvironmentBuildError, tomllib.TOMLDecodeError) as exc:
        return None, [f"pyproject.toml could not be parsed safely: {type(exc).__name__}"]

    project = payload.get("project")
    if isinstance(project, dict):
        dynamic = project.get("dynamic")
        if isinstance(dynamic, list) and "dependencies" in dynamic:
            return None, ["dynamic PEP 621 dependencies are not supported"]
        dependencies = project.get("dependencies")
        if dependencies is not None:
            if not isinstance(dependencies, list) or not all(
                isinstance(item, str) for item in dependencies
            ):
                return None, ["PEP 621 dependencies must be a static string list"]
            values = [item.strip() for item in dependencies if item.strip()]
            if len(values) > _MAX_REQUIREMENT_LINES:
                return None, ["pyproject dependency list is too large"]
            if any(len(item) > _MAX_REQUIREMENT_LINE_CHARS for item in values):
                return None, ["pyproject dependency entry is too long"]
            return values, []

    poetry = payload.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict) and "dependencies" in poetry:
        dependencies = poetry.get("dependencies")
        if not isinstance(dependencies, dict):
            return None, ["Poetry dependencies must be a static mapping"]
        generated: list[str] = []
        for name, constraint in dependencies.items():
            if str(name).lower() == "python":
                continue
            if not isinstance(constraint, str) or not re.fullmatch(
                r"\d+(?:\.\d+){1,3}",
                constraint.strip(),
            ):
                return None, [
                    (
                        "only exact Poetry dependency versions can be converted "
                        "without invoking project build code"
                    )
                ]
            generated.append(f"{name}=={constraint.strip()}")
        return generated, []

    return [], []


def _setup_cfg_runtime_requirements(
    path: Path,
) -> tuple[list[str] | None, list[str]]:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(_read_dependency_text(path))
    except (EnvironmentBuildError, configparser.Error) as exc:
        return None, [f"setup.cfg could not be parsed safely: {type(exc).__name__}"]
    raw = parser.get("options", "install_requires", fallback="")
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(values) > _MAX_REQUIREMENT_LINES:
        return None, ["setup.cfg dependency list is too large"]
    if any(len(item) > _MAX_REQUIREMENT_LINE_CHARS for item in values):
        return None, ["setup.cfg dependency entry is too long"]
    return values, []


def _generated_metadata_plan(
    *,
    source: Path,
    requirements: list[str] | None,
    parse_errors: list[str],
    base_image: str,
) -> BuildPlan:
    if requirements is None:
        return BuildPlan(
            builder="python-generated-metadata",
            base_image=base_image,
            dependency_file=source.name,
            dependency_sha256=sha256_file(source),
            dependency_precision="floating",
            dockerfile=(
                f"FROM {base_image}\\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\\n"
                "WORKDIR /workspace\\n"
            ),
            network_required=False,
            safe_manifest_only=False,
            rejected_reasons=parse_errors,
        )
    if not requirements:
        return BuildPlan(
            builder="python-generated-metadata",
            base_image=base_image,
            dependency_file=source.name,
            dependency_sha256=sha256_file(source),
            dependency_precision="base-only",
            dockerfile=(
                f"FROM {base_image}\\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\\n"
                "WORKDIR /workspace\\n"
            ),
            network_required=False,
            safe_manifest_only=True,
        )

    rejected = audit_requirement_lines(requirements)
    return BuildPlan(
        builder="python-generated-metadata",
        base_image=base_image,
        dependency_file=source.name,
        dependency_sha256=sha256_file(source),
        dependency_precision=classify_requirement_lines(requirements),
        dockerfile=(
            f"FROM {base_image}\\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\\n"
            "COPY agnxiv-generated-requirements.txt /tmp/requirements.txt\\n"
            "RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt\\n"
            "WORKDIR /workspace\\n"
        ),
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
        generated_requirements=requirements,
    )


def classify_dependency_precision(path: str | Path) -> Literal[
    "floating",
    "version-pinned",
    "hash-pinned",
]:
    """Classify how precisely a requirements file identifies dependencies."""
    requirement_path = Path(path)
    return classify_requirement_lines(_active_requirement_lines(requirement_path))


def audit_requirements(path: str | Path) -> list[str]:
    """Return reasons a requirements file needs stronger build isolation."""
    return audit_requirement_lines(_active_requirement_lines(Path(path)))


def plan_python_environment(
    repository: str | Path,
    *,
    base_image: str = "python:3.11-slim",
) -> BuildPlan:
    """Create a dependency-only environment build plan.

    The generated context contains dependency metadata only, never the research
    repository itself.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    requirements = root / "requirements.txt"
    root_conda = next(
        (
            path
            for path in (root / "environment.yml", root / "environment.yaml")
            if path.exists()
        ),
        None,
    )

    if requirements.is_symlink():
        raise ValueError("requirements.txt symlinks are not allowed")

    if not requirements.exists():
        conda_manifest = root_conda or discover_referenced_nested_conda(root)
        if conda_manifest is not None:
            if conda_manifest.is_symlink():
                raise ValueError("Conda environment symlinks are not allowed")
            return _conda_environment_plan(
                conda_manifest,
                root=root,
                base_image=base_image,
            )

        pyproject = root / "pyproject.toml"
        setup_cfg = root / "setup.cfg"
        setup_py = root / "setup.py"

        if pyproject.is_symlink() or setup_cfg.is_symlink() or setup_py.is_symlink():
            raise ValueError("dependency metadata symlinks are not allowed")

        if pyproject.exists():
            generated, errors = _pyproject_runtime_requirements(pyproject)
            return _generated_metadata_plan(
                source=pyproject,
                requirements=generated,
                parse_errors=errors,
                base_image=base_image,
            )

        if setup_cfg.exists():
            generated, errors = _setup_cfg_runtime_requirements(setup_cfg)
            return _generated_metadata_plan(
                source=setup_cfg,
                requirements=generated,
                parse_errors=errors,
                base_image=base_image,
            )

        if setup_py.exists():
            return BuildPlan(
                builder="python-generated-metadata",
                base_image=base_image,
                dependency_file="setup.py",
                dependency_sha256=sha256_file(setup_py),
                dependency_precision="floating",
                dockerfile=(
                    f"FROM {base_image}\n"
                    "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
                    "WORKDIR /workspace\n"
                ),
                network_required=False,
                safe_manifest_only=False,
                rejected_reasons=[
                    (
                        "setup.py cannot be executed or copied into the network-enabled "
                        "dependency build context"
                    )
                ],
            )

        return BuildPlan(
            base_image=base_image,
            dependency_file=None,
            dependency_sha256=None,
            dependency_precision="base-only",
            dockerfile=(
                f"FROM {base_image}\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
                "WORKDIR /workspace\n"
            ),
            network_required=False,
            safe_manifest_only=True,
        )

    try:
        _read_dependency_text(requirements)
    except EnvironmentBuildError as exc:
        return BuildPlan(
            base_image=base_image,
            dependency_file="requirements.txt",
            dependency_sha256=None,
            dependency_precision="floating",
            dockerfile=(
                f"FROM {base_image}\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
                "WORKDIR /workspace\n"
            ),
            network_required=False,
            safe_manifest_only=False,
            rejected_reasons=[str(exc)],
        )

    rejected = audit_requirements(requirements)
    dockerfile = (
        f"FROM {base_image}\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "COPY requirements.txt /tmp/requirements.txt\n"
        "RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt\n"
        "WORKDIR /workspace\n"
    )
    return BuildPlan(
        base_image=base_image,
        dependency_file="requirements.txt",
        dependency_sha256=sha256_file(requirements),
        dependency_precision=classify_dependency_precision(requirements),
        dockerfile=dockerfile,
        network_required=True,
        safe_manifest_only=not rejected,
        rejected_reasons=rejected,
    )


def build_python_environment(
    repository: str | Path,
    *,
    base_image: str = "python:3.11-slim",
    timeout_seconds: int = 1200,
) -> BuildResult:
    """Build a runtime without exposing research source to dependency installers."""
    root = Path(repository)
    plan = plan_python_environment(root, base_image=base_image)

    if not plan.safe_manifest_only:
        reasons = "; ".join(plan.rejected_reasons)
        raise EnvironmentBuildError(
            "dependency manifest requires stronger isolation and was rejected: "
            + reasons
        )

    try:
        base_image_id_before = resolve_local_image_id(base_image)
    except (SandboxError, ValueError) as exc:
        raise EnvironmentBuildError(
            "base image must already exist locally before environment construction"
        ) from exc

    image_ref = f"agnxiv-env:{plan.plan_id[:24]}"

    with tempfile.TemporaryDirectory(prefix="agnxiv-build-") as temp:
        context = Path(temp)
        (context / "Dockerfile").write_text(plan.dockerfile, encoding="utf-8")

        if plan.builder == "conda-micromamba-metadata":
            (context / "agnxiv-generated-environment.yml").write_text(
                "\n".join(plan.generated_requirements) + "\n",
                encoding="utf-8",
            )
        elif plan.generated_requirements:
            (context / "agnxiv-generated-requirements.txt").write_text(
                "\n".join(plan.generated_requirements) + "\n",
                encoding="utf-8",
            )
        elif plan.dependency_file is not None:
            shutil.copyfile(
                root / plan.dependency_file,
                context / plan.dependency_file,
            )

        command = [
            "docker",
            "build",
            "--quiet",
            "--pull=false",
            "--network",
            "default" if plan.network_required else "none",
            "--tag",
            image_ref,
            str(context),
        ]

        def limit_build_output() -> None:
            if os.name != "posix":
                return
            import resource

            resource.setrlimit(
                resource.RLIMIT_FSIZE,
                (_MAX_BUILD_OUTPUT_BYTES, _MAX_BUILD_OUTPUT_BYTES),
            )

        try:
            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                completed = subprocess.run(
                    command,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=timeout_seconds,
                    check=False,
                    preexec_fn=limit_build_output if os.name == "posix" else None,
                )
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout_bytes = stdout_file.read(_MAX_BUILD_OUTPUT_BYTES + 1)
                stderr_bytes = stderr_file.read(_MAX_BUILD_OUTPUT_BYTES + 1)
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentBuildError(f"environment build failed: {exc}") from exc

    if (
        len(stdout_bytes) > _MAX_BUILD_OUTPUT_BYTES
        or len(stderr_bytes) > _MAX_BUILD_OUTPUT_BYTES
    ):
        raise EnvironmentBuildError("environment build exceeded output limit")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        message = stderr[-4000:] or stdout[-4000:]
        raise EnvironmentBuildError(
            f"environment build exited with {completed.returncode}: {message}"
        )

    base_image_id_after = resolve_local_image_id(base_image)
    if base_image_id_after != base_image_id_before:
        raise EnvironmentBuildError(
            "base image changed during environment construction; build rejected"
        )

    image_id = resolve_local_image_id(image_ref)
    return BuildResult(
        plan=plan,
        image_ref=image_ref,
        image_id=image_id,
        base_image_id=base_image_id_before,
        stdout_sha256=hashlib.sha256(stdout_bytes).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr_bytes).hexdigest(),
    )
