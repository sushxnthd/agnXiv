from pathlib import Path
from types import SimpleNamespace

import pytest

from agnxiv.build import (
    EnvironmentBuildError,
    audit_requirements,
    build_python_environment,
    classify_dependency_precision,
    plan_python_environment,
)


def test_manifest_only_build_plan(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "numpy==2.1.0\npandas==2.2.3\n",
        encoding="utf-8",
    )
    plan = plan_python_environment(tmp_path)

    assert plan.safe_manifest_only is True
    assert plan.network_required is True
    assert plan.dependency_sha256 is not None
    assert plan.dependency_precision == "version-pinned"
    assert "COPY requirements.txt" in plan.dockerfile


def test_floating_requirements_are_identified(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy>=1.24\nscipy>=1.10\n",
        encoding="utf-8",
    )

    assert classify_dependency_precision(requirements) == "floating"
    assert plan_python_environment(tmp_path).dependency_precision == "floating"


def test_hash_pinned_requirements_are_identified(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy==2.1.0 --hash=sha256:abcdef\n",
        encoding="utf-8",
    )

    assert classify_dependency_precision(requirements) == "hash-pinned"


def test_rejects_vcs_and_editable_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "-e .\ngit+https://example.invalid/research.git\n",
        encoding="utf-8",
    )

    reasons = audit_requirements(requirements)
    assert len(reasons) == 2
    assert plan_python_environment(tmp_path).safe_manifest_only is False


def test_rejects_direct_urls_and_custom_indices(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "--extra-index-url https://packages.example.invalid/simple\n"
        "pkg @ https://packages.example.invalid/pkg.whl\n",
        encoding="utf-8",
    )

    assert len(audit_requirements(requirements)) == 2


def test_runtime_build_context_excludes_research_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (tmp_path / "secret_research.py").write_text("SECRET = True\n", encoding="utf-8")

    seen_context_files: list[str] = []

    def fake_resolve(image: str) -> str:
        return "sha256:built" if image.startswith("agnxiv-env:") else "sha256:base"

    def fake_run(command, **kwargs):
        context = Path(command[-1])
        seen_context_files.extend(
            sorted(path.name for path in context.iterdir() if path.is_file())
        )
        assert not (context / "secret_research.py").exists()
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("agnxiv.build.resolve_local_image_id", fake_resolve)
    monkeypatch.setattr("agnxiv.build.subprocess.run", fake_run)

    result = build_python_environment(tmp_path)

    assert seen_context_files == ["Dockerfile", "requirements.txt"]
    assert result.base_image_id == "sha256:base"
    assert result.image_id == "sha256:built"


def test_unsafe_manifest_is_rejected_before_build(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("-e .\n", encoding="utf-8")

    with pytest.raises(EnvironmentBuildError):
        build_python_environment(tmp_path)


def test_symlinked_requirements_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "outside-requirements.txt"
    target.write_text("numpy==2.1.0\n", encoding="utf-8")
    link = tmp_path / "requirements.txt"

    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError, match="symlinks are not allowed"):
        plan_python_environment(tmp_path)


def test_pyproject_dependencies_are_materialized_without_research_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "paper"\n'
        'version = "0.1.0"\n'
        'dependencies = ["numpy==2.1.0", "scipy>=1.10"]\n',
        encoding="utf-8",
    )
    (tmp_path / "secret_research.py").write_text("SECRET = True\n", encoding="utf-8")
    plan = plan_python_environment(tmp_path)
    assert plan.builder == "python-generated-metadata"
    assert plan.dependency_file == "pyproject.toml"
    assert plan.generated_requirements == ["numpy==2.1.0", "scipy>=1.10"]
    assert plan.dependency_precision == "floating"
    assert "COPY agnxiv-generated-requirements.txt" in plan.dockerfile

    seen: list[str] = []

    def fake_resolve(image: str) -> str:
        return "sha256:built" if image.startswith("agnxiv-env:") else "sha256:base"

    def fake_run(command, **kwargs):
        context = Path(command[-1])
        seen.extend(sorted(path.name for path in context.iterdir() if path.is_file()))
        generated = context / "agnxiv-generated-requirements.txt"
        assert generated.read_text(encoding="utf-8") == "numpy==2.1.0\nscipy>=1.10\n"
        assert not (context / "pyproject.toml").exists()
        assert not (context / "secret_research.py").exists()
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("agnxiv.build.resolve_local_image_id", fake_resolve)
    monkeypatch.setattr("agnxiv.build.subprocess.run", fake_run)
    build_python_environment(tmp_path)
    assert seen == ["Dockerfile", "agnxiv-generated-requirements.txt"]


def test_setup_cfg_dependencies_are_materialized_statically(tmp_path: Path) -> None:
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = paper\n"
        "[options]\ninstall_requires =\n"
        "    numpy==2.1.0\n"
        "    scipy==1.14.1\n",
        encoding="utf-8",
    )
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is True
    assert plan.dependency_precision == "version-pinned"
    assert plan.generated_requirements == ["numpy==2.1.0", "scipy==1.14.1"]


def test_dynamic_pyproject_dependencies_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "paper"\n'
        'version = "0.1.0"\n'
        'dynamic = ["dependencies"]\n',
        encoding="utf-8",
    )
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is False
    assert any("dynamic PEP 621" in reason for reason in plan.rejected_reasons)


def test_setup_py_without_static_manifest_is_not_executed_during_build(
    tmp_path: Path,
) -> None:
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(install_requires=['numpy'])\n",
        encoding="utf-8",
    )
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is False
    with pytest.raises(EnvironmentBuildError):
        build_python_environment(tmp_path)


def test_oversized_requirements_fail_closed_before_build(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_bytes(b"numpy==2.1.0\n" + b"#" * (2 * 1024 * 1024))
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is False
    assert any("byte limit" in reason for reason in plan.rejected_reasons)
    with pytest.raises(EnvironmentBuildError):
        build_python_environment(tmp_path)


def test_oversized_dependency_line_fails_closed(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pkg==" + "1" * 9000 + "\n", encoding="utf-8")
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is False
    assert any("oversized line" in reason for reason in plan.rejected_reasons)


def test_oversized_pyproject_is_not_parsed_or_executed(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(
        b'[project]\nname="paper"\nversion="0.1.0"\n'
        + b"#" * (2 * 1024 * 1024)
    )
    plan = plan_python_environment(tmp_path)
    assert plan.safe_manifest_only is False
    assert any("EnvironmentBuildError" in reason for reason in plan.rejected_reasons)


def test_readme_referenced_nested_pinned_conda_uses_metadata_only_builder(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "examples" / "NLU"
    nested.mkdir(parents=True)
    (tmp_path / "README.md").write_text(
        "Use examples/NLU/ to reproduce the paper.\n",
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='paper')\n",
        encoding="utf-8",
    )
    (nested / "environment.yml").write_text(
        "name: paper\n"
        "channels:\n"
        "  - pytorch\n"
        "  - defaults\n"
        "dependencies:\n"
        "  - python=3.7.10=h12debd9_4\n"
        "  - numpy=1.20.2=py37h2d18471_0\n"
        "  - pip=21.1.3=py37h06a4308_0\n"
        "  - pip:\n"
        "    - datasets==1.9.0\n"
        "prefix: /old/machine/path\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path, base_image="python:3.7-slim")

    assert plan.builder == "conda-micromamba-metadata"
    assert plan.safe_manifest_only is True
    assert plan.dependency_precision == "version-pinned"
    assert plan.dependency_file == "examples/NLU/environment.yml"
    assert "micromamba digest mismatch" in plan.dockerfile
    assert "COPY agnxiv-generated-environment.yml" in plan.dockerfile
    assert all(not line.startswith("prefix:") for line in plan.generated_requirements)


def test_nested_conda_requires_explicit_readme_reference(tmp_path: Path) -> None:
    nested = tmp_path / "examples" / "NLU"
    nested.mkdir(parents=True)
    (tmp_path / "README.md").write_text("No environment path here.\n", encoding="utf-8")
    (nested / "environment.yml").write_text(
        "channels:\n  - defaults\ndependencies:\n  - python=3.10.14\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path)

    assert plan.builder != "conda-micromamba-metadata"


def test_conda_builder_rejects_floating_or_untrusted_metadata(tmp_path: Path) -> None:
    (tmp_path / "environment.yml").write_text(
        "channels:\n"
        "  - attacker.example\n"
        "dependencies:\n"
        "  - python=3.11\n"
        "  - numpy>=1.20\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path)

    assert plan.builder == "conda-micromamba-metadata"
    assert plan.safe_manifest_only is False
    assert any("untrusted Conda channel" in x for x in plan.rejected_reasons)
    assert any("not exactly pinned" in x for x in plan.rejected_reasons)


def test_conda_builder_rejects_inline_yaml_channel_bypass(tmp_path: Path) -> None:
    (tmp_path / "environment.yml").write_text(
        "name: paper\n"
        "channels: [defaults, attacker.example]\n"
        "dependencies:\n"
        "  - python=3.11.9\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path)

    assert plan.builder == "conda-micromamba-metadata"
    assert plan.safe_manifest_only is False
    assert any("unsupported top-level Conda metadata" in x for x in plan.rejected_reasons)


def test_conda_builder_rejects_activation_variables(tmp_path: Path) -> None:
    (tmp_path / "environment.yml").write_text(
        "name: paper\n"
        "channels:\n"
        "  - defaults\n"
        "dependencies:\n"
        "  - python=3.11.9\n"
        "variables:\n"
        "  PIP_INDEX_URL: https://attacker.invalid/simple\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path)

    assert plan.safe_manifest_only is False
    assert any("unsupported top-level Conda metadata" in x for x in plan.rejected_reasons)
