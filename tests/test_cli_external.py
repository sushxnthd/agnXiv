import json

from typer.testing import CliRunner

from agnxiv.cli import app

runner = CliRunner()


def _ready():
    return {
        "schema": "agnxiv.readiness/1",
        "ready": True,
        "checks": {
            "git": {"ready": True},
            "docker_cli": {"ready": True},
            "docker_daemon": {"ready": True},
            "pdf_support": {"ready": True},
        },
    }


def test_verify_external_exports_conservative_result(tmp_path, monkeypatch) -> None:
    output = tmp_path / "audit.json"
    monkeypatch.setattr("agnxiv.cli._external_prerequisites", _ready)
    monkeypatch.setattr(
        "agnxiv.hosted_runner.execute_job",
        lambda **kwargs: (
            "needs_review",
            {
                "kind": "verification",
                "bundle": {"record": {"verdict": "UNABLE_TO_VERIFY"}},
            },
        ),
    )

    result = runner.invoke(
        app,
        [
            "verify-external",
            "--repository", "owner/repository",
            "--repository-ref", "a" * 40,
            "--arxiv-id", "2604.15702v2",
            "--expected-manuscript-sha256", "b" * 64,
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "agnxiv.external-run/1"
    assert payload["status"] == "needs_review"
    assert payload["result"]["bundle"]["record"]["verdict"] == "UNABLE_TO_VERIFY"
    assert payload["readiness"]["ready"] is True


def test_verify_external_exports_setup_failure(tmp_path, monkeypatch) -> None:
    output = tmp_path / "audit.json"
    not_ready = _ready()
    not_ready["ready"] = False
    not_ready["checks"]["docker_daemon"] = {
        "ready": False,
        "remediation": "Start Docker.",
    }
    monkeypatch.setattr("agnxiv.cli._external_prerequisites", lambda: not_ready)

    result = runner.invoke(
        app,
        [
            "verify-external",
            "--repository", "owner/repository",
            "--repository-ref", "a" * 40,
            "--arxiv-id", "2604.15702v2",
            "--expected-manuscript-sha256", "b" * 64,
            "--output", str(output),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert payload["readiness"]["checks"]["docker_daemon"]["ready"] is False


def test_doctor_fails_closed_when_sandbox_is_unavailable(monkeypatch) -> None:
    not_ready = _ready()
    not_ready["ready"] = False
    monkeypatch.setattr("agnxiv.cli._external_prerequisites", lambda: not_ready)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 2
    assert json.loads(result.output)["ready"] is False
