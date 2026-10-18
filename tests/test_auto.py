from pathlib import Path

from agnxiv.auto import build_auto_plan


def test_auto_plan_generates_draft_but_abstains_without_locator(tmp_path: Path) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text(
        "Our model achieves accuracy of 91.4% on the test set.",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (repo / "evaluate.py").write_text(
        "print('accuracy: 91.4%')\n",
        encoding="utf-8",
    )

    plan = build_auto_plan(paper, repo)

    assert plan.draft_spec is not None
    assert plan.safe_to_execute is False
    assert plan.automation_score >= 0.7
    assert any(stage.name == "observation_locator" and not stage.complete for stage in plan.stages)


def test_auto_plan_detects_historical_dependency_warning(tmp_path: Path) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text("The F1 score improves by 10%.", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("gensim>=1.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "To completely reproduce the results in our paper, install an older version "
        "of gensim version 0.10.2.\n"
        "python evaluate.py --benchmark paper\n",
        encoding="utf-8",
    )
    (repo / "evaluate.py").write_text("print('f1: 0.5')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert any("historical dependency" in blocker for blocker in plan.blockers)
    assert plan.warnings
    assert plan.safe_to_execute is False
