import json
from pathlib import Path

from agnxiv.models import Verdict
from agnxiv.sandbox import ExecutionResult
from agnxiv.spec import (
    VerificationSpec,
    execute_verification_spec,
    load_verification_spec,
)


def test_loads_versioned_verification_spec(tmp_path: Path) -> None:
    spec_path = tmp_path / "agnxiv.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema_version": "agnxiv.spec/1",
                "repository": ".",
                "claim": {
                    "id": "C1",
                    "text": "Accuracy is 91.4%.",
                    "metric": "accuracy",
                    "reported_value": 0.914,
                    "unit": "fraction",
                },
                "policy": {
                    "kind": "relative",
                    "operator": "approx",
                    "tolerance": 0.01,
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "evaluate.py"],
                },
                "observation": {
                    "kind": "json_path",
                    "value": "metrics.accuracy",
                },
            }
        ),
        encoding="utf-8",
    )

    spec = load_verification_spec(spec_path)

    assert isinstance(spec, VerificationSpec)
    assert spec.schema_version == "agnxiv.spec/1"
    assert spec.observation.kind == "json_path"


def test_executes_and_binds_verification_spec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "evaluate.py").write_text("print('{}')\n", encoding="utf-8")
    spec_path = tmp_path / "agnxiv.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema_version": "agnxiv.spec/1",
                "repository": ".",
                "claim": {
                    "id": "C1",
                    "text": "Accuracy is 91.4%.",
                    "metric": "accuracy",
                    "reported_value": 0.914,
                },
                "policy": {
                    "kind": "relative",
                    "operator": "approx",
                    "tolerance": 0.01,
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "evaluate.py"],
                },
                "observation": {
                    "kind": "json_path",
                    "value": "metrics.accuracy",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_execute_in_docker(**kwargs):
        return ExecutionResult(
            command=("docker", "run"),
            image_id="sha256:test",
            artifact_mounts=(),
            returncode=0,
            stdout='{"metrics": {"accuracy": 0.914}}\n',
            stderr="",
        )

    monkeypatch.setattr("agnxiv.pipeline.execute_in_docker", fake_execute_in_docker)

    bundle = execute_verification_spec(spec_path)

    assert bundle.record.verdict == Verdict.VERIFIED
    assert bundle.verification_spec_sha256 is not None
    assert bundle.observation_method == "explicit_json_path"
