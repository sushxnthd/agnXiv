from pathlib import Path

from agnxiv.auto import build_auto_plan, score_claim_centrality
from agnxiv.models import Claim, ClaimSource


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


def test_auto_plan_orders_generated_intermediate(tmp_path: Path) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text(
        "The method achieves Micro-F1 of 42.4%.",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "trainer --input data.mat --output learned.embeddings\n"
        "python scoring.py --emb learned.embeddings --network data.mat\n",
        encoding="utf-8",
    )
    (repo / "data.mat").write_bytes(b"fixture")
    (repo / "scoring.py").write_text("print('Micro-F1: 42.4%')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert plan.draft_spec is not None
    assert plan.draft_spec.runtime.commands is not None
    assert len(plan.draft_spec.runtime.commands) == 2
    assert not any("missing local inputs" in blocker for blocker in plan.blockers)
    workflow_stage = next(
        stage for stage in plan.stages if stage.name == "workflow_ordering"
    )
    assert workflow_stage.complete is True


def test_auto_plan_prefers_explicit_contribution_over_reference_metric(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text(
        "The accuracy of a reference classifier is 76.6% and is included for reference. "
        "Our proposed method achieves accuracy of 92.4% and outperforms the baseline.",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (repo / "evaluate.py").write_text(
        "print('accuracy: 92.4%')\n",
        encoding="utf-8",
    )

    plan = build_auto_plan(paper, repo)

    assert plan.claims
    assert "proposed method" in plan.claims[0].claim.text.lower()


def test_auto_plan_selects_single_evaluation_target_over_lifecycle_commands(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text(
        "Our proposed method achieves MAE of 3.2.",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "python process.py --config data.yaml\n"
        "python train.py --config model.yaml\n"
        "python test.py --config eval.yaml\n",
        encoding="utf-8",
    )
    for name in ("process.py", "train.py", "test.py"):
        (repo / name).write_text("print('mae: 3.2')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    workflow_stage = next(
        stage for stage in plan.stages if stage.name == "workflow_ordering"
    )
    assert workflow_stage.complete is True
    assert plan.draft_spec is not None
    assert plan.draft_spec.runtime.command == ["python", "test.py", "--config", "eval.yaml"]


def test_auto_plan_abstains_when_multiple_evaluation_targets_are_documented(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.txt"
    paper.write_text("Our method achieves accuracy of 90%.", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("numpy==2.1.0\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "python test.py --config dataset_a.yaml\n"
        "python test.py --config dataset_b.yaml\n",
        encoding="utf-8",
    )
    (repo / "test.py").write_text("print('accuracy: 90%')\n", encoding="utf-8")

    plan = build_auto_plan(paper, repo)

    assert any(
        "execution order could not be inferred safely" in blocker
        for blocker in plan.blockers
    )


def test_centrality_prefers_early_primary_efficiency_result() -> None:
    primary = Claim(
        id="primary",
        text=(
            "Compared with full fine-tuning, the proposed method can reduce "
            "trainable parameters by 10,000 times and memory by 3 times."
        ),
        reported_value=10000,
        unit="times",
        source=ClaimSource(page=1),
    )
    later = Claim(
        id="later",
        text="We also observe a 25% speedup during a later training analysis.",
        metric="speedup",
        reported_value=0.25,
        unit="fraction",
        source=ClaimSource(page=5),
    )

    assert score_claim_centrality(
        primary,
        evidence_score=0.95,
    ) > score_claim_centrality(
        later,
        evidence_score=0.80,
    )


def test_centrality_score_is_discovery_only_and_bounded() -> None:
    claim = Claim(
        id="central",
        text=(
            "Our model significantly outperforms the state of the art and "
            "accelerates decoding by 64x."
        ),
        reported_value=64,
        unit="x",
        source=ClaimSource(page=1),
    )

    score = score_claim_centrality(claim, evidence_score=1.0)

    assert 0.0 <= score <= 1.0
