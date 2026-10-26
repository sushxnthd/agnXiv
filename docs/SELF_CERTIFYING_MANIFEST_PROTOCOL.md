# Frozen protocol: repository self-certification boundary

Status: frozen before implementation.

## Question

Can a repository author control the hosted verification manifest, executable,
claim, reported value, and output, then obtain a definitive scientific verdict
without any independent verification authority?

## Attack

Construct repository-supplied `agnxiv.json` manifests whose commands emit the
reported value directly. The output is syntactically valid, the command exits
successfully, and the locked runtime/provenance gates all pass, but the
execution supplies no evidence independent of the claim source.

The old baseline is predicted to return `VERIFIED` for every such case because
the numeric verifier cannot distinguish computation from self-assertion.

## Correction prediction

Hosted `verify_spec` jobs must mark their verification authority as
`repository_supplied`. Any otherwise decisive verdict from that authority is
retained as a provisional result for audit but published as
`UNABLE_TO_VERIFY`, with an explicit self-certification blocker. Auto-planned
verification remains a separate path and is not reclassified by this change.

## Frozen boundary sweep

- 128 direct self-echo attacks across exact and tolerance policies.
- 32 repository-manifest controls that perform genuine arithmetic; these must
  also remain conditional because output quality cannot establish independent
  authority.
- Existing environment, image, dependency, and manuscript provenance gates.
- Direct unit tests showing that the same raw bundle remains decisive when it
  is not labelled repository-supplied.
- Independent standard-library replay that imports no agnXiv production code.

## Publishable threshold

- Old baseline false-passes 128/128 self-echo attacks.
- Corrected hosted manifest gate has zero definitive false passes.
- Provisional verdict, numeric evidence, and explicit blocker are preserved.
- Non-repository-supplied controls are unchanged.
- Full regression, deterministic evidence, and independent audit pass.

## Claim boundary

This does not detect fabricated code or establish scientific correctness. It
enforces a narrower epistemic rule: a party cannot be both the sole source of a
verification procedure and the authority for a definitive agnXiv verdict.

## Kill condition

Kill the kernel if repository-supplied manifests can still publish a decisive
verdict, if the raw provisional evidence is lost, or if the gate suppresses
verification bundles that are not labelled repository-supplied.
