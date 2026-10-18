from pathlib import Path

from agnxiv.build import audit_requirements, plan_python_environment


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
