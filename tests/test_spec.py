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


def test_runtime_supports_ordered_command_sequence(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "stage1.py").write_text("print('stage1')\n", encoding="utf-8")
    (tmp_path / "stage2.py").write_text("print('stage2')\n", encoding="utf-8")
    spec_path = tmp_path / "agnxiv-multistage.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema_version": "agnxiv.spec/1",
                "repository": ".",
                "claim": {
                    "id": "C1",
                    "text": "Accuracy is 91.4%.",
                    "metric": "accuracy",
                    "reported_value": 0.914
                },
                "policy": {
                    "kind": "relative",
                    "operator": "approx",
                    "tolerance": 0.01
                },
                "runtime": {
                    "image": "local:test",
                    "commands": [
                        ["python", "stage1.py"],
                        ["python", "stage2.py"]
                    ]
                },
                "observation": {
                    "kind": "json_path",
                    "value": "metrics.accuracy"
                }
            }
        ),
        encoding="utf-8",
    )

    captured: list[list[str]] = []

    def fake_verify_with_command(claim, repository, **kwargs):
        from agnxiv.environment import EnvironmentSpec
        from agnxiv.models import Observation
        from agnxiv.pipeline import VerificationBundle
        from agnxiv.provenance import fingerprint_tree
        from agnxiv.verify import verify_numeric_claim

        captured.append(kwargs["command"])
        record = verify_numeric_claim(
            claim,
            [Observation(value=0.914)],
            kwargs["policy"],
        )
        return VerificationBundle(
            claim=claim,
            provenance=fingerprint_tree(repository),
            environment=EnvironmentSpec(),
            record=record,
        )

    monkeypatch.setattr("agnxiv.spec.verify_with_command", fake_verify_with_command)

    bundle = execute_verification_spec(spec_path)

    assert bundle.record.verdict == Verdict.VERIFIED
    assert len(captured) == 1
    assert captured[0][:2] == ["sh", "-lc"]
    assert "python stage1.py && python stage2.py" in captured[0][2]


def test_runtime_rejects_command_and_commands_together() -> None:
    import pytest

    with pytest.raises(ValueError):
        VerificationSpec.model_validate(
            {
                "schema_version": "agnxiv.spec/1",
                "claim": {
                    "id": "C1",
                    "text": "Result is 1.",
                    "reported_value": 1.0
                },
                "policy": {
                    "kind": "absolute",
                    "operator": "approx",
                    "tolerance": 0.0
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "a.py"],
                    "commands": [["python", "b.py"]]
                }
            }
        )


@pytest.mark.parametrize(
    "pattern",
    [
        r"(?P<value>(a+)+)$",
        r"(?P<value>(a|aa)+)$",
        r"(?=(?P<value>\d+))",
    ],
)
def test_manifest_rejects_unsafe_regex_locator(pattern: str) -> None:
    with pytest.raises(ValueError, match="unsafe or unsupported"):
        VerificationSpec.model_validate(
            {
                "schema_version": "agnxiv.spec/1",
                "claim": {"id": "C1", "text": "Result", "reported_value": 1.0},
                "policy": {
                    "kind": "absolute",
                    "operator": "approx",
                    "tolerance": 0.01,
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "run.py"],
                },
                "observation": {"kind": "regex", "value": pattern},
            }
        )


@pytest.mark.parametrize("scale", [float("inf"), float("-inf"), float("nan"), 1e12])
def test_manifest_rejects_unbounded_observation_scale(scale: float) -> None:
    with pytest.raises(ValueError, match="scale"):
        VerificationSpec.model_validate(
            {
                "schema_version": "agnxiv.spec/1",
                "claim": {"id": "C1", "text": "Result", "reported_value": 1.0},
                "policy": {
                    "kind": "absolute",
                    "operator": "approx",
                    "tolerance": 0.01,
                },
                "runtime": {
                    "image": "local:test",
                    "command": ["python", "run.py"],
                },
                "observation": {
                    "kind": "json_path",
                    "value": "result",
                    "scale": scale,
                },
            }
        )
