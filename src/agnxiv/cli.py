from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from .attestation import attest_bundle
from .auto import build_auto_plan
from .benchmark import load_jsonl_cases, run_recorded_benchmark
from .build import EnvironmentBuildError, build_python_environment
from .challenge import assess_repeated_observations
from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .models import Claim, Observation, VerificationPolicy
from .pipeline import inspect_project, verify_with_command
from .preprint import parse_arxiv_reference
from .spec import execute_verification_spec
from .statement import (
    AttestationSignatureError,
    DSSEEnvelope,
    build_verification_statement,
    generate_ed25519_keypair,
    sign_statement_ed25519,
    verify_statement_ed25519,
)
from .verify import verify_numeric_claim

app = typer.Typer(
    no_args_is_help=True,
    help="AgnXiv — executable verification for computational research claims.",
)


def _policy(
    kind: str,
    tolerance: float,
    minimum_repetitions: int = 1,
    operator: str = "approx",
) -> VerificationPolicy:
    if kind not in {"relative", "absolute"}:
        raise typer.BadParameter("kind must be 'relative' or 'absolute'")
    if operator not in {"approx", "at_least", "at_most"}:
        raise typer.BadParameter(
            "operator must be 'approx', 'at_least', or 'at_most'"
        )
    validated_kind = cast(Literal["relative", "absolute"], kind)
    validated_operator = cast(
        Literal["approx", "at_least", "at_most"],
        operator,
    )
    return VerificationPolicy(
        kind=validated_kind,
        operator=validated_operator,
        tolerance=tolerance,
        minimum_repetitions=minimum_repetitions,
    )


@app.command("claims")
def claims_command(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Extract candidate quantitative claims from a PDF or text file."""
    if path.suffix.lower() == ".pdf":
        claims = extract_claims_from_pdf(path)
    else:
        claims = extract_quantitative_claims(
            path.read_text(encoding="utf-8"),
            manuscript=path.name,
        )
    typer.echo(json.dumps([claim.model_dump(mode="json") for claim in claims], indent=2))


@app.command("auto-plan")
def auto_plan_command(
    manuscript: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    repository: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
) -> None:
    """Generate a conservative verification plan without a hand-written manifest."""
    plan = build_auto_plan(manuscript, repository)
    typer.echo(plan.model_dump_json(indent=2))


@app.command("arxiv-id")
def arxiv_id_command(
    value: Annotated[str, typer.Argument()],
) -> None:
    """Normalize an arXiv identifier while preserving its exact version."""
    typer.echo(parse_arxiv_reference(value).model_dump_json(indent=2))


def _external_prerequisites() -> dict:
    """Return machine-readable readiness for the external-paper CLI path."""
    git_path = shutil.which("git")
    docker_path = shutil.which("docker")
    checks = {
        "git": {
            "ready": git_path is not None,
            "path": git_path,
            "remediation": None if git_path else "Install Git and ensure `git` is on PATH.",
        },
        "docker_cli": {
            "ready": docker_path is not None,
            "path": docker_path,
            "remediation": (
                None
                if docker_path
                else "Install Docker Engine or Docker Desktop and ensure `docker` is on PATH."
            ),
        },
        "pdf_support": {
            "ready": importlib.util.find_spec("pypdf") is not None,
            "path": None,
            "remediation": (
                None
                if importlib.util.find_spec("pypdf") is not None
                else "Install the PDF extra with `python -m pip install 'agnxiv[pdf]'`."
            ),
        },
    }
    daemon_ready = False
    daemon_detail = "Docker CLI is unavailable."
    if docker_path is not None:
        try:
            completed = subprocess.run(
                [docker_path, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            daemon_ready = completed.returncode == 0 and bool(completed.stdout.strip())
            daemon_detail = (
                completed.stdout.strip()
                if daemon_ready
                else (completed.stderr.strip() or completed.stdout.strip() or "Docker daemon unavailable.")
            )
        except (OSError, subprocess.SubprocessError) as exc:
            daemon_detail = str(exc)
    checks["docker_daemon"] = {
        "ready": daemon_ready,
        "path": None,
        "detail": daemon_detail,
        "remediation": None if daemon_ready else "Start the Docker daemon and retry `agnxiv doctor`.",
    }
    return {
        "schema": "agnxiv.readiness/1",
        "ready": all(item["ready"] for item in checks.values()),
        "checks": checks,
    }


def _write_export(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@app.command("doctor")
def doctor_command() -> None:
    """Check whether this machine can run a sandboxed external-paper verification."""
    readiness = _external_prerequisites()
    typer.echo(json.dumps(readiness, indent=2))
    if not readiness["ready"]:
        raise typer.Exit(code=2)


@app.command("verify-external")
def verify_external_command(
    repository: Annotated[
        str,
        typer.Option(help="Public GitHub owner/repository slug."),
    ],
    repository_ref: Annotated[
        str,
        typer.Option(help="Pinned Git commit or immutable Git ref."),
    ],
    arxiv_id: Annotated[
        str,
        typer.Option(help="Versioned arXiv identifier, for example 2604.15702v2."),
    ],
    expected_manuscript_sha256: Annotated[
        str,
        typer.Option(help="Expected SHA-256 of the exact downloaded manuscript."),
    ],
    output: Annotated[
        Path,
        typer.Option(dir_okay=False, help="New JSON audit-record path."),
    ],
) -> None:
    """Run one pinned public paper/repository workflow and export its audit record."""
    from .hosted_runner import HostedRunnerError, execute_job

    if output.exists():
        raise typer.BadParameter("refusing to overwrite an existing audit record")

    readiness = _external_prerequisites()
    payload: dict = {
        "schema": "agnxiv.external-run/1",
        "status": "failed",
        "result": None,
        "error": None,
        "readiness": readiness,
    }
    if not readiness["ready"]:
        payload["error"] = "local sandbox prerequisites are not ready; run `agnxiv doctor`"
        _write_export(output, payload)
        typer.echo(json.dumps({"status": "failed", "output": str(output), "error": payload["error"]}))
        raise typer.Exit(code=2)

    try:
        status, result = execute_job(
            mode="auto_verify",
            repository=repository,
            repository_ref=repository_ref,
            arxiv_id=arxiv_id,
            spec_path=None,
            expected_manuscript_sha256=expected_manuscript_sha256,
        )
        payload["status"] = status
        payload["result"] = result
    except HostedRunnerError as exc:
        payload["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - durable top-level CLI failure boundary
        payload["error"] = f"unexpected verifier failure: {type(exc).__name__}: {exc}"

    _write_export(output, payload)
    typer.echo(
        json.dumps(
            {
                "status": payload["status"],
                "output": str(output),
                "error": payload["error"],
            }
        )
    )
    if payload["status"] == "failed":
        raise typer.Exit(code=2)


@app.command("keygen")
def keygen_command(
    private_out: Annotated[Path, typer.Option()],
    public_out: Annotated[Path, typer.Option()],
) -> None:
    """Generate an Ed25519 issuer keypair for AgnXiv DSSE attestations."""
    if private_out.exists() or public_out.exists():
        raise typer.BadParameter("refusing to overwrite an existing key file")

    private_key, public_key, key_id = generate_ed25519_keypair()
    private_out.parent.mkdir(parents=True, exist_ok=True)
    public_out.parent.mkdir(parents=True, exist_ok=True)
    private_out.write_bytes(private_key)
    public_out.write_bytes(public_key)
    os.chmod(private_out, 0o600)
    typer.echo(
        json.dumps(
            {
                "key_id": key_id,
                "private_key": str(private_out),
                "public_key": str(public_out),
            },
            indent=2,
        )
    )


@app.command("verify-envelope")
def verify_envelope_command(
    envelope_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    public_key: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Verify a DSSE signature and emit the authenticated in-toto statement."""
    try:
        envelope = DSSEEnvelope.model_validate_json(
            envelope_path.read_text(encoding="utf-8")
        )
        statement = verify_statement_ed25519(envelope, public_key.read_bytes())
    except (AttestationSignatureError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(json.dumps(statement, indent=2))


@app.command("inspect")
def inspect_command(
    repository: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    expected: Annotated[float, typer.Option()],
    metric: Annotated[str, typer.Option()],
    unit: Annotated[str | None, typer.Option()] = None,
    claim_text: Annotated[str, typer.Option()] = "CLI inspection claim",
) -> None:
    """Fingerprint a project and show candidate evidence and execution commands."""
    claim = Claim(
        id="CLI-INSPECT",
        text=claim_text,
        metric=metric,
        reported_value=expected,
        unit=unit,
    )
    provenance, environment, evidence, commands = inspect_project(claim, repository)
    payload = {
        "claim": claim.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "environment": environment.model_dump(mode="json"),
        "evidence_candidates": [item.model_dump(mode="json") for item in evidence],
        "command_candidates": [item.model_dump(mode="json") for item in commands],
    }
    typer.echo(json.dumps(payload, indent=2))


@app.command("build-env")
def build_env_command(
    repository: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    base_image: Annotated[str, typer.Option()] = "python:3.11-slim",
) -> None:
    """Build a manifest-only runtime and return its immutable image identity."""
    try:
        result = build_python_environment(repository, base_image=base_image)
    except EnvironmentBuildError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(result.model_dump_json(indent=2))


@app.command("verify-spec")
def verify_spec_command(
    spec_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    sign_key: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
) -> None:
    """Execute one declarative AgnXiv verification manifest."""
    try:
        bundle = execute_verification_spec(spec_path)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    attestation = attest_bundle(bundle)
    statement = build_verification_statement(bundle)
    response = {
        "bundle": bundle.model_dump(mode="json"),
        "attestation": attestation.model_dump(mode="json"),
        "statement": statement,
    }
    if sign_key is not None:
        envelope = sign_statement_ed25519(statement, sign_key.read_bytes())
        response["dsseEnvelope"] = envelope.model_dump(mode="json")

    typer.echo(json.dumps(response, indent=2, default=str))


@app.command("verify-number")
def verify_number_command(
    expected: Annotated[float, typer.Option(help="Value reported by the paper.")],
    observed: Annotated[
        list[float],
        typer.Option("--observed", help="Observed value; repeat for multiple runs."),
    ],
    tolerance: Annotated[
        float,
        typer.Option(help="Relative fraction by default (0.01 = 1%)."),
    ] = 0.01,
    kind: Annotated[str, typer.Option(help="'relative' or 'absolute'.")] = "relative",
    operator: Annotated[
        str,
        typer.Option(help="'approx', 'at_least', or 'at_most'."),
    ] = "approx",
    minimum_repetitions: Annotated[int, typer.Option(min=1)] = 1,
) -> None:
    """Apply AgnXiv's deterministic verifier to a numeric claim."""
    claim = Claim(
        id="CLI-001",
        text="CLI verification",
        reported_value=expected,
    )
    policy = _policy(kind, tolerance, minimum_repetitions, operator)
    record = verify_numeric_claim(
        claim,
        [Observation(value=value) for value in observed],
        policy,
    )
    typer.echo(record.model_dump_json(indent=2))


@app.command("verify-command")
def verify_command(
    repository: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    image: Annotated[
        str,
        typer.Option(help="Locally available container image."),
    ],
    command: Annotated[
        list[str],
        typer.Option("--cmd", help="Command token; repeat for each token."),
    ],
    expected: Annotated[float, typer.Option()],
    metric: Annotated[str, typer.Option()],
    manuscript: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
    sign_key: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
    artifact: Annotated[
        list[Path] | None,
        typer.Option(
            "--artifact",
            exists=True,
            readable=True,
            help="External dataset/checkpoint; repeat to bind multiple artifacts.",
        ),
    ] = None,
    unit: Annotated[str | None, typer.Option()] = None,
    claim_text: Annotated[str, typer.Option()] = "CLI execution claim",
    tolerance: Annotated[float, typer.Option()] = 0.01,
    kind: Annotated[str, typer.Option()] = "relative",
    operator: Annotated[str, typer.Option()] = "approx",
    json_path: Annotated[str | None, typer.Option()] = None,
    output_regex: Annotated[str | None, typer.Option()] = None,
    observation_scale: Annotated[float, typer.Option()] = 1.0,
) -> None:
    """Run one explicit command and emit an auditable verification bundle."""
    if json_path is not None and output_regex is not None:
        raise typer.BadParameter("json-path and output-regex are mutually exclusive")

    claim = Claim(
        id="CLI-RUN",
        text=claim_text,
        metric=metric,
        reported_value=expected,
        unit=unit,
    )
    bundle = verify_with_command(
        claim,
        repository,
        image=image,
        command=command,
        policy=_policy(kind, tolerance, operator=operator),
        manuscript_path=manuscript,
        artifact_paths=artifact,
        json_path=json_path,
        output_regex=output_regex,
        observation_scale=observation_scale,
    )
    attestation = attest_bundle(bundle)
    statement = build_verification_statement(bundle)
    response = {
        "bundle": bundle.model_dump(mode="json"),
        "attestation": attestation.model_dump(mode="json"),
        "statement": statement,
    }
    if sign_key is not None:
        envelope = sign_statement_ed25519(statement, sign_key.read_bytes())
        response["dsseEnvelope"] = envelope.model_dump(mode="json")

    typer.echo(json.dumps(response, indent=2, default=str))


@app.command("robustness")
def robustness_command(
    expected: Annotated[float, typer.Option()],
    observed: Annotated[list[float], typer.Option("--observed")],
    tolerance: Annotated[float, typer.Option()] = 0.01,
    kind: Annotated[str, typer.Option()] = "relative",
    operator: Annotated[str, typer.Option()] = "approx",
    minimum_pass_fraction: Annotated[float, typer.Option()] = 0.8,
    minimum_repetitions: Annotated[int, typer.Option(min=1)] = 5,
) -> None:
    """Assess repeated observations without conflating robustness with reproduction."""
    claim = Claim(id="CLI-ROBUST", text="CLI robustness claim", reported_value=expected)
    summary = assess_repeated_observations(
        claim,
        [Observation(value=value) for value in observed],
        _policy(kind, tolerance, operator=operator),
        minimum_pass_fraction=minimum_pass_fraction,
        minimum_repetitions=minimum_repetitions,
    )
    typer.echo(summary.model_dump_json(indent=2))


@app.command("benchmark")
def benchmark_command(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Run a recorded-output benchmark and report false-pass rate."""
    report = run_recorded_benchmark(load_jsonl_cases(path))
    typer.echo(report.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
