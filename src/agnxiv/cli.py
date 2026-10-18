from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from .attestation import attest_bundle
from .challenge import assess_repeated_observations
from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .models import Claim, Observation, VerificationPolicy
from .pipeline import inspect_project, verify_with_command
from .verify import verify_numeric_claim

app = typer.Typer(
    no_args_is_help=True,
    help="AgnXiv — executable verification for computational research claims.",
)


def _policy(kind: str, tolerance: float, minimum_repetitions: int = 1) -> VerificationPolicy:
    if kind not in {"relative", "absolute"}:
        raise typer.BadParameter("kind must be 'relative' or 'absolute'")
    validated_kind = cast(Literal["relative", "absolute"], kind)
    return VerificationPolicy(
        kind=validated_kind,
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
    minimum_repetitions: Annotated[int, typer.Option(min=1)] = 1,
) -> None:
    """Apply AgnXiv's deterministic verifier to a numeric claim."""
    claim = Claim(
        id="CLI-001",
        text="CLI verification",
        reported_value=expected,
    )
    policy = _policy(kind, tolerance, minimum_repetitions)
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
    unit: Annotated[str | None, typer.Option()] = None,
    claim_text: Annotated[str, typer.Option()] = "CLI execution claim",
    tolerance: Annotated[float, typer.Option()] = 0.01,
    kind: Annotated[str, typer.Option()] = "relative",
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
        policy=_policy(kind, tolerance),
    )
    attestation = attest_bundle(bundle)
    typer.echo(
        json.dumps(
            {
                "bundle": bundle.model_dump(mode="json"),
                "attestation": attestation.model_dump(mode="json"),
            },
            indent=2,
            default=str,
        )
    )


@app.command("robustness")
def robustness_command(
    expected: Annotated[float, typer.Option()],
    observed: Annotated[list[float], typer.Option("--observed")],
    tolerance: Annotated[float, typer.Option()] = 0.01,
    kind: Annotated[str, typer.Option()] = "relative",
    minimum_pass_fraction: Annotated[float, typer.Option()] = 0.8,
    minimum_repetitions: Annotated[int, typer.Option(min=1)] = 5,
) -> None:
    """Assess repeated observations without conflating robustness with reproduction."""
    claim = Claim(id="CLI-ROBUST", text="CLI robustness claim", reported_value=expected)
    summary = assess_repeated_observations(
        claim,
        [Observation(value=value) for value in observed],
        _policy(kind, tolerance),
        minimum_pass_fraction=minimum_pass_fraction,
        minimum_repetitions=minimum_repetitions,
    )
    typer.echo(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
