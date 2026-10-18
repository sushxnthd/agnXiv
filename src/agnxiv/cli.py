from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from .attestation import attest_bundle
from .benchmark import load_jsonl_cases, run_recorded_benchmark
from .build import EnvironmentBuildError, build_python_environment
from .challenge import assess_repeated_observations
from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .models import Claim, Observation, VerificationPolicy
from .pipeline import inspect_project, verify_with_command
from .preprint import parse_arxiv_reference
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


@app.command("arxiv-id")
def arxiv_id_command(
    value: Annotated[str, typer.Argument()],
) -> None:
    """Normalize an arXiv identifier while preserving its exact version."""
    typer.echo(parse_arxiv_reference(value).model_dump_json(indent=2))


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
    observation_scale: Annotated[float, typer.Option()] = 1.0,
) -> None:
    """Run one explicit command and emit an auditable verification bundle."""
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
