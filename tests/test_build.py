from pathlib import Path
from types import SimpleNamespace

import pytest

from agnxiv.build import (
    EnvironmentBuildError,
    audit_requirements,
    bind_plan_to_immutable_base,
    build_python_environment,
    classify_dependency_precision,
    copy_frozen_dependency_manifest,
    plan_python_environment,
    read_build_output_image_id,
)

BUILT_ID = "sha256:" + "b" * 64
ATTACKER_ID = "sha256:" + "c" * 64
BASE_ID = "sha256:" + "d" * 64


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
        "numpy==2.1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    assert classify_dependency_precision(requirements) == "hash-pinned"
    assert "pip install --no-cache-dir --require-hashes" in plan_python_environment(
        tmp_path
    ).dockerfile


def test_comment_smuggled_hash_cannot_upgrade_requirement(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy==2.1.0 # --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    plan = plan_python_environment(tmp_path)
    assert classify_dependency_precision(requirements) == "version-pinned"
    assert plan.dependency_precision == "version-pinned"
    assert "--require-hashes" not in plan.dockerfile


def test_mixed_real_and_comment_hashes_are_not_hash_pinned(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy==2.1.0 --hash=sha256:" + "a" * 64 + "\n"
        "pandas==2.2.3 # --hash=sha256:" + "b" * 64 + "\n",
        encoding="utf-8",
    )

    assert classify_dependency_precision(requirements) == "version-pinned"


def test_build_plan_binds_from_to_repository_digest(tmp_path: Path) -> None:
    plan = plan_python_environment(tmp_path, base_image="python:3.11-slim")
    immutable = "python@sha256:" + "a" * 64
    bound = bind_plan_to_immutable_base(plan, immutable)

    assert bound.base_image == immutable
    assert bound.dockerfile.startswith(f"FROM {immutable}\n")
    assert "FROM python:3.11-slim\n" not in bound.dockerfile
    assert bound.plan_id != plan.plan_id


def test_frozen_manifest_copy_rejects_content_drift(tmp_path: Path) -> None:
    source = tmp_path / "requirements.txt"
    destination = tmp_path / "context-requirements.txt"
    source.write_text("numpy==2.1.0\n", encoding="utf-8")
    expected = "f" * 64

    with pytest.raises(EnvironmentBuildError, match="changed after build planning"):
        copy_frozen_dependency_manifest(
            source,
            destination,
            expected_sha256=expected,
        )


def test_partial_hashes_cannot_upgrade_an_unhashed_dependency(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy==2.1.0 --hash=sha256:" + "a" * 64 + "\n"
        "pandas==2.2.3\n",
        encoding="utf-8",
    )

    assert classify_dependency_precision(requirements) == "version-pinned"


def test_multiline_hashes_are_bound_to_each_requirement(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "numpy==2.1.0 \\\n"
        "  --hash=sha256:" + "a" * 64 + "\n"
        "pandas==2.2.3 \\\n"
        "  --hash=sha256:" + "b" * 64 + "\n",
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
        return ATTACKER_ID if image.startswith("agnxiv-env:") else BASE_ID

    def fake_run(command, **kwargs):
        context = Path(command[-1])
        seen_context_files.extend(
            sorted(path.name for path in context.iterdir() if path.is_file())
        )
        assert not (context / "secret_research.py").exists()
        Path(command[command.index("--iidfile") + 1]).write_text(
            BUILT_ID + "\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("agnxiv.build.resolve_local_image_id", fake_resolve)
    monkeypatch.setattr(
        "agnxiv.build.resolve_local_image_digest_ref",
        lambda image: "python@sha256:" + "a" * 64,
    )
    monkeypatch.setattr("agnxiv.build.subprocess.run", fake_run)

    result = build_python_environment(tmp_path)

    assert seen_context_files == ["Dockerfile", "requirements.txt"]
    assert result.base_image_id == BASE_ID
    assert result.image_id == BUILT_ID
    assert result.plan.base_image == "python@sha256:" + "a" * 64
    assert seen_context_files == ["Dockerfile", "requirements.txt"]


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


def test_runtime_build_uses_selected_nested_requirements_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scoped = tmp_path / "examples" / "eval"
    scoped.mkdir(parents=True)
    (scoped / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (tmp_path / "secret_research.py").write_text("SECRET = True\n", encoding="utf-8")

    seen_requirements: list[str] = []

    def fake_resolve(image: str) -> str:
        return ATTACKER_ID if image.startswith("agnxiv-env:") else BASE_ID

    def fake_run(command, **kwargs):
        context = Path(command[-1])
        assert sorted(path.name for path in context.iterdir()) == [
            "Dockerfile",
            "requirements.txt",
        ]
        assert not (context / "secret_research.py").exists()
        seen_requirements.append(
            (context / "requirements.txt").read_text(encoding="utf-8")
        )
        Path(command[command.index("--iidfile") + 1]).write_text(
            BUILT_ID + "\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("agnxiv.build.resolve_local_image_id", fake_resolve)
    monkeypatch.setattr(
        "agnxiv.build.resolve_local_image_digest_ref",
        lambda image: "python@sha256:" + "a" * 64,
    )
    monkeypatch.setattr("agnxiv.build.subprocess.run", fake_run)

    result = build_python_environment(
        tmp_path,
        dependency_file="examples/eval/requirements.txt",
    )

    assert result.plan.dependency_file == "examples/eval/requirements.txt"
    assert seen_requirements == ["numpy==2.1.0\n"]


def test_build_identity_comes_from_iidfile_not_mutable_tag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    resolved: list[str] = []

    def fake_resolve(image: str) -> str:
        resolved.append(image)
        return ATTACKER_ID if image.startswith("agnxiv-env:") else BASE_ID

    def fake_run(command, **kwargs):
        Path(command[command.index("--iidfile") + 1]).write_text(
            BUILT_ID + "\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("agnxiv.build.resolve_local_image_id", fake_resolve)
    monkeypatch.setattr(
        "agnxiv.build.resolve_local_image_digest_ref",
        lambda image: "python@sha256:" + "a" * 64,
    )
    monkeypatch.setattr("agnxiv.build.subprocess.run", fake_run)

    result = build_python_environment(tmp_path)

    assert result.image_id == BUILT_ID
    assert not any(image.startswith("agnxiv-env:") for image in resolved)


@pytest.mark.parametrize(
    "payload",
    [None, "", "sha256:not-a-digest\n", BUILT_ID + "\n" + ATTACKER_ID + "\n"],
)
def test_build_identity_evidence_fails_closed(tmp_path: Path, payload: str | None) -> None:
    iidfile = tmp_path / "image-id"
    if payload is not None:
        iidfile.write_text(payload, encoding="utf-8")

    with pytest.raises(EnvironmentBuildError, match="image identity evidence"):
        read_build_output_image_id(iidfile)


def test_nested_dependency_manifest_must_stay_inside_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        plan_python_environment(tmp_path, dependency_file="../requirements.txt")
