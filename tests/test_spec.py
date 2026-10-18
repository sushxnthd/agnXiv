import json
from pathlib import Path

import pytest

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


def _write_minimal_spec(path: Path, repository: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "agnxiv.spec/1",
                "repository": repository,
                "claim": {
                    "id": "C1",
                    "text": "Result is 1.0.",
                    "reported_value": 1.0,
                },
                "policy": {
                    "kind": "absolute",
                    "operator": "approx",
                    "tolerance": 0.0,
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "run.py"],
                },
            }
        ),
        encoding="utf-8",
    )


def test_manifest_rejects_parent_directory_escape(tmp_path: Path) -> None:
    spec_path = tmp_path / "agnxiv-escape.json"
    _write_minimal_spec(spec_path, "../outside")

    with pytest.raises(ValueError, match="escapes the verification workspace"):
        execute_verification_spec(spec_path)


def test_manifest_rejects_absolute_repository_path(tmp_path: Path) -> None:
    spec_path = tmp_path / "agnxiv-absolute.json"
    absolute = str((tmp_path.parent / "outside").resolve())
    _write_minimal_spec(spec_path, absolute)

    with pytest.raises(ValueError, match="must be relative"):
        execute_verification_spec(spec_path)
