from pathlib import Path
from types import SimpleNamespace

import pytest

from agnxiv.build import (
    EnvironmentBuildError,
    audit_requirements,
    build_python_environment,
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
    assert "COPY requirements.txt" in plan.dockerfile


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
