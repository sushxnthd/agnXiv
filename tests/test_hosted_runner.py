from pathlib import Path

import pytest
from pypdf import PdfWriter

from agnxiv.hosted_runner import (
    HostedRunnerError,
    _validate_hosted_image,
    checkout_repository,
    execute_job,
    extract_pdf_claims_isolated,
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


def test_isolated_pdf_parser_accepts_small_valid_pdf(tmp_path: Path) -> None:
    paper = tmp_path / "paper.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with paper.open("wb") as handle:
        writer.write(handle)

    claims = extract_pdf_claims_isolated(paper, tmp_path)
    assert claims == []


def test_isolated_pdf_parser_rejects_malformed_pdf(tmp_path: Path) -> None:
    paper = tmp_path / "bad.pdf"
    paper.write_bytes(b"%PDF-1.7\nnot-a-valid-pdf")

    with pytest.raises(HostedRunnerError, match="safely parse"):
        extract_pdf_claims_isolated(paper, tmp_path)


def test_repository_checkout_disables_lfs_smudge_and_submodule_recursion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands: list[list[str]] = []
    destination = tmp_path / "repo"

    def fake_run(command: list[str], *, timeout: int = 300):
        commands.append(command)
        if "clone" in command:
            destination.mkdir(parents=True)
        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""
        return Completed()

    monkeypatch.setattr("agnxiv.hosted_runner._run", fake_run)
    checkout_repository("owner/repo", "main", destination)

    checkout = next(command for command in commands if "checkout" in command)
    joined = " ".join(checkout)
    assert "filter.lfs.smudge=" in joined
    assert "filter.lfs.process=" in joined
    assert "filter.lfs.required=false" in joined
    assert "submodule.recurse=false" in joined
