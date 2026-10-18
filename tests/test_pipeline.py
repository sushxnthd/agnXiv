from pathlib import Path

from agnxiv.models import Claim, Verdict, VerificationPolicy
from agnxiv.pipeline import verify_with_command
from agnxiv.sandbox import ExecutionResult


def test_pipeline_contradicts_mismatched_executed_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "evaluate.py").write_text(
        "print('accuracy: 82.4%')\n",
        encoding="utf-8",
    )

    def fake_execute_in_docker(**kwargs):
        return ExecutionResult(
            command=("docker", "run", "sha256:test", "python", "evaluate.py"),
            image_id="sha256:test",
            returncode=0,
            stdout="accuracy: 82.4%\n",
            stderr="",
        )

    monkeypatch.setattr("agnxiv.pipeline.execute_in_docker", fake_execute_in_docker)

    claim = Claim(
        id="C1",
        text="The model achieves accuracy of 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    bundle = verify_with_command(
        claim,
        tmp_path,
        image="local:test",
        command=["python", "evaluate.py"],
        policy=VerificationPolicy(kind="relative", tolerance=0.01),
    )

    assert bundle.record.verdict == Verdict.CONTRADICTED
    assert bundle.execution is not None
    assert bundle.execution.source_unchanged is True
    assert bundle.execution.image_id == "sha256:test"


def test_pipeline_abstains_on_ambiguous_output(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "run.py").write_text("print('0.9 1.0')\n", encoding="utf-8")

    def fake_execute_in_docker(**kwargs):
        return ExecutionResult(
            command=("docker", "run"),
            image_id="sha256:test",
            returncode=0,
            stdout="0.9\n1.0\n",
            stderr="",
        )

    monkeypatch.setattr("agnxiv.pipeline.execute_in_docker", fake_execute_in_docker)

    claim = Claim(id="C1", text="Result is 1.0.", reported_value=1.0)
    bundle = verify_with_command(
        claim,
        tmp_path,
        image="local:test",
        command=["python", "run.py"],
        policy=VerificationPolicy(kind="relative", tolerance=0.01),
    )

    assert bundle.record.verdict == Verdict.UNABLE_TO_VERIFY
