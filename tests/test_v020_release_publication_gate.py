import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results/v020_release_publication_gate/results.json"
AUDIT = ROOT / "results/v020_release_publication_gate/audit.json"


def test_v020_release_publication_gate_has_zero_false_passes():
    subprocess.run(
        [
            sys.executable,
            "scripts/verify_v020_release_publication_gate.py",
            "matrix",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "scripts/audit_v020_release_publication_gate.py"],
        cwd=ROOT,
        check=True,
    )
    result = json.loads(RESULT.read_text())
    audit = json.loads(AUDIT.read_text())

    assert result["overall_passed"] is True
    assert result["preflight"] == {
        "accepted_controls": 3,
        "false_passes": 0,
        "false_rejects": 0,
        "rejected_cases": 61,
        "total_cases": 64,
    }
    assert result["postdraft_assets"] == {
        "accepted_controls": 1,
        "false_passes": 0,
        "false_rejects": 0,
        "rejected_cases": 1023,
        "total_cases": 1024,
    }
    assert audit["passed"] is True
    assert audit["production_imports"] == 0
    assert audit["workflow_ordering"]["asset_gate_before_publication"] is True
