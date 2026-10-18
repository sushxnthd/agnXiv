from pathlib import Path

import pytest

from agnxiv.hosted_runner import HostedRunnerError, execute_job


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
