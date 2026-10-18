from pathlib import Path

import pytest

from agnxiv.evidence import map_claim_to_repository
from agnxiv.models import Claim


def test_evidence_mapper_finds_reported_value(tmp_path: Path) -> None:
    script = tmp_path / "evaluate.py"
    script.write_text(
        'print("test accuracy: 91.4%")\n',
        encoding="utf-8",
    )
    claim = Claim(
        id="C1",
        text="The model achieves test accuracy of 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    candidates = map_claim_to_repository(claim, tmp_path)
    assert candidates
    assert candidates[0].ref.path is not None
    assert candidates[0].ref.path.startswith("evaluate.py:")


def test_evidence_mapper_does_not_read_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / "agnxiv-evidence-outside.py"
    outside.write_text('print("test accuracy: 91.4%")\n', encoding="utf-8")
    link = tmp_path / "evaluate.py"

    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    claim = Claim(
        id="C1",
        text="The model achieves test accuracy of 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )

    assert map_claim_to_repository(claim, tmp_path) == []
