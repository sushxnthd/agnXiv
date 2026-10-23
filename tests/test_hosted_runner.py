from pathlib import Path

import pytest

from agnxiv.hosted_runner import (
    HostedRunnerError,
    _validate_hosted_image,
    _verify_manuscript_identity,
    execute_job,
)


def test_hosted_verify_spec_rejects_repository_escape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_checkout(slug: str, ref: str, destination: Path) -> None:
        destination.mkdir(parents=True)
        (destination / "agnxiv.json").write_text(
            """
{
  "schema_version": "agnxiv.spec/1",
  "repository": "../outside",
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
    "image": "python:3.11-slim",
    "command": ["python", "run.py"]
  }
}
""".strip(),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "agnxiv.hosted_runner.checkout_repository",
        fake_checkout,
    )

    with pytest.raises(
        HostedRunnerError,
        match="escapes its workspace",
    ):
        execute_job(
            mode="verify_spec",
            repository="owner/repository",
            repository_ref="main",
            arxiv_id=None,
            spec_path="agnxiv.json",
        )


def test_hosted_runtime_allowlist() -> None:
    assert _validate_hosted_image("python:3.11-slim") == "python:3.11-slim"
    assert (
        _validate_hosted_image("python:3.11.17-slim-bookworm")
        == "python:3.11.17-slim-bookworm"
    )

    with pytest.raises(HostedRunnerError, match="approved official Python"):
        _validate_hosted_image("ubuntu:latest")

    with pytest.raises(HostedRunnerError, match="approved official Python"):
        _validate_hosted_image("attacker/research-runtime:latest")


def test_malformed_manuscript_digest_fails_before_checkout(monkeypatch) -> None:
    checkout_calls = 0

    def fake_checkout(*args, **kwargs) -> None:
        nonlocal checkout_calls
        checkout_calls += 1

    monkeypatch.setattr("agnxiv.hosted_runner.checkout_repository", fake_checkout)

    with pytest.raises(HostedRunnerError, match="64 hexadecimal"):
        execute_job(
            mode="auto_verify",
            repository="owner/repository",
            repository_ref="abc123",
            arxiv_id="2604.15702v2",
            spec_path=None,
            expected_manuscript_sha256="not-a-digest",
        )

    assert checkout_calls == 0


def test_matching_manuscript_digest_returns_versioned_identity(tmp_path: Path) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"exact manuscript bytes")
    digest = "b1633bf26c9b04de855eb37e15be091a1c3e2199b9f74323900289095a412498"

    assert _verify_manuscript_identity(
        paper,
        arxiv_id="2604.15702v2",
        expected_sha256=digest,
    ) == {
        "arxiv_id": "2604.15702v2",
        "sha256": digest,
        "expected_sha256": digest,
        "identity_verified": True,
    }


def test_manuscript_digest_mismatch_fails_before_planning_or_execution(
    monkeypatch,
) -> None:
    calls = {"plan": 0, "build": 0, "execute": 0}

    def fake_checkout(slug: str, ref: str, destination: Path) -> None:
        destination.mkdir(parents=True)

    def fake_download(arxiv_id: str, destination: Path) -> None:
        destination.write_bytes(b"mutated manuscript")

    def forbidden(name: str):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} must not run after identity mismatch")

        return fail

    monkeypatch.setattr("agnxiv.hosted_runner.checkout_repository", fake_checkout)
    monkeypatch.setattr("agnxiv.hosted_runner.download_arxiv_pdf", fake_download)
    monkeypatch.setattr("agnxiv.hosted_runner.build_auto_plan", forbidden("plan"))
    monkeypatch.setattr("agnxiv.hosted_runner.build_python_environment", forbidden("build"))
    monkeypatch.setattr("agnxiv.hosted_runner.run_zero_manifest", forbidden("execute"))

    with pytest.raises(HostedRunnerError, match="manuscript SHA-256 mismatch"):
        execute_job(
            mode="auto_verify",
            repository="owner/repository",
            repository_ref="abc123",
            arxiv_id="2604.15702v2",
            spec_path=None,
            expected_manuscript_sha256="0" * 64,
        )

    assert calls == {"plan": 0, "build": 0, "execute": 0}
