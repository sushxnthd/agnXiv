import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v020_candidate_version_and_release_evidence_gate_are_bound():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/release-candidate.yml").read_text(
        encoding="utf-8"
    )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    gate = (ROOT / "docs/RELEASE_CANDIDATE_0_2_0.md").read_text(encoding="utf-8")

    assert metadata["project"]["version"] == "0.2.0"
    assert "0.2.0 - release candidate" in changelog
    assert "python -m build --sdist --wheel" in workflow
    assert "agnxiv-0.2.0-py3-none-any.whl[pdf]" in workflow
    assert "/tmp/agnxiv-release-venv/bin/agnxiv doctor" in workflow
    assert "/tmp/agnxiv-release-venv/bin/agnxiv verify-external" in workflow
    assert '"schema": "agnxiv.release-candidate/1"' in workflow
    assert '"published_release": False' in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "does not authorize" in " ".join(gate.split())
