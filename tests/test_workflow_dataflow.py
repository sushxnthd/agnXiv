from pathlib import Path

from agnxiv.auto import _option_paths, build_auto_plan
from agnxiv.planner import CommandCandidate


def _paper_and_repo(tmp_path: Path) -> tuple[Path, Path]:
    paper = tmp_path / "paper.txt"
    paper.write_text(
        "Our proposed method achieves accuracy of 91.4% on the test set.",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    return paper, repo


def test_equals_style_file_flags_order_the_workflow(tmp_path: Path) -> None:
    paper, repo = _paper_and_repo(tmp_path)
    (repo / "README.md").write_text(
        "python prepare.py --output_path=cache/features.npy\n"
        "python evaluate.py --input=cache/features.npy\n",
        encoding="utf-8",
    )
    (repo / "prepare.py").write_text("print('preparation')\n", encoding="utf-8")
    (repo / "evaluate.py").write_text("print('accuracy: 91.4%')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert plan.draft_spec is not None
    assert plan.draft_spec.runtime.commands == [
        ["python", "prepare.py", "--output_path=cache/features.npy"],
        ["python", "evaluate.py", "--input=cache/features.npy"],
    ]
    workflow = next(x for x in plan.stages if x.name == "workflow_ordering")
    assert workflow.complete
    assert not any("missing local inputs" in b for b in plan.blockers)
    assert not plan.safe_to_execute  # Explicit output locator is still required.


def test_ambiguous_artifact_producers_block_unattended_plan(tmp_path: Path) -> None:
    paper, repo = _paper_and_repo(tmp_path)
    (repo / "README.md").write_text(
        "python prepare.py --output=cache/features.npy\n"
        "python convert.py --output=cache/features.npy\n"
        "python evaluate.py --input cache/features.npy\n",
        encoding="utf-8",
    )
    (repo / "evaluate.py").write_text("print('accuracy: 91.4%')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert any(
        "Multiple documented commands produce the same required artifact" in blocker
        for blocker in plan.blockers
    )
    workflow = next(x for x in plan.stages if x.name == "workflow_ordering")
    assert not workflow.complete
    assert not plan.safe_to_execute


def test_traversing_output_is_not_inferred_as_safe_dependency(tmp_path: Path) -> None:
    paper, repo = _paper_and_repo(tmp_path)
    (repo / "README.md").write_text(
        "python prepare.py --output=../cache/features.npy\n"
        "python evaluate.py --input=cache/features.npy\n",
        encoding="utf-8",
    )
    (repo / "evaluate.py").write_text("print('accuracy: 91.4%')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert any("missing local inputs: cache/features.npy" in b for b in plan.blockers)
    assert not plan.safe_to_execute


def test_supported_flag_aliases_and_normalized_relative_paths() -> None:
    candidate = CommandCandidate(
        command=[
            "python",
            "run.py",
            "--output-file",
            "./results/scores.json",
            "--save_path=models/checkpoint.pt",
            "--output=/tmp/out.json",
        ],
        source="README.md",
        score=0.9,
        rationale="test",
    )
    flags = {"--output-file", "--save_path", "--output"}
    assert _option_paths(candidate, flags) == {
        "results/scores.json",
        "models/checkpoint.pt",
    }
