from __future__ import annotations

import json
from pathlib import Path

import typer

from .claims import extract_claims_from_pdf, extract_quantitative_claims
from .models import Claim, Observation, VerificationPolicy
from .verify import verify_numeric_claim

app = typer.Typer(
    no_args_is_help=True,
    help="AgnXiv — executable verification for computational research claims.",
)


@app.command("claims")
def claims_command(
    path: Path = typer.Argument(..., exists=True, readable=True),
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


@app.command("verify-number")
def verify_number_command(
    expected: float = typer.Option(..., help="Value reported by the paper."),
    observed: list[float] = typer.Option(
        ..., "--observed", help="Observed value; repeat for multiple runs."
    ),
    tolerance: float = typer.Option(
        0.01, help="Relative fraction by default (0.01 = 1%)."
    ),
    kind: str = typer.Option("relative", help="'relative' or 'absolute'."),
    minimum_repetitions: int = typer.Option(1, min=1),
) -> None:
    """Apply AgnXiv's deterministic verifier to a numeric claim."""
    if kind not in {"relative", "absolute"}:
        raise typer.BadParameter("kind must be 'relative' or 'absolute'")

    claim = Claim(
        id="CLI-001",
        text="CLI verification",
        reported_value=expected,
    )
    policy = VerificationPolicy(
        kind=kind,  # type: ignore[arg-type]
        tolerance=tolerance,
        minimum_repetitions=minimum_repetitions,
    )
    record = verify_numeric_claim(
        claim,
        [Observation(value=value) for value in observed],
        policy,
    )
    typer.echo(record.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
