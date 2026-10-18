from pathlib import Path

import pytest

from agnxiv.evidence import (\n    build_repository_evidence_index,\n    map_claim_to_index,\n    map_claim_to_repository,\n)
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


def test_repository_index_is_reused_for_multiple_claims(tmp_path: Path) -> None:
    (tmp_path / "evaluate.py").write_text(
        'print("accuracy: 91.4%")\nprint("f1: 88.0%")\n',
        encoding="utf-8",
    )
    index = build_repository_evidence_index(tmp_path)

    accuracy = Claim(
        id="C1",
        text="Accuracy is 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    f1 = Claim(
        id="C2",
        text="F1 is 88.0%.",
        metric="f1",
        reported_value=0.88,
        unit="fraction",
    )

    assert index.scanned_files == 1
    assert map_claim_to_index(accuracy, index)
    assert map_claim_to_index(f1, index)


def test_repository_index_prioritizes_project_code_over_examples(
    tmp_path: Path,
) -> None:
    project = tmp_path / "package"
    project.mkdir()
    (project / "core.py").write_text("metric = 1\n", encoding="utf-8")
    examples = tmp_path / "examples"
    examples.mkdir()
    for index in range(20):
        (examples / f"demo_{index}.py").write_text(
            "value = 1\n" * 20,
            encoding="utf-8",
        )

    index = build_repository_evidence_index(tmp_path, line_budget=5)

    assert any(item.path == "package/core.py" for item in index.lines)
