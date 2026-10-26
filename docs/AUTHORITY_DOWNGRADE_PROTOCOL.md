# Frozen protocol: verification-authority downgrade

Status: frozen before implementation.

## Threat

The hosted verdict gate blocks a bundle labelled `repository_supplied`, but the
bundle schema currently permits the authority field to be absent. The gate
treats that absence as non-blocking. Deleting the label from an otherwise
identical self-certifying bundle can therefore convert provisional evidence
back into a definitive scientific verdict.

This is a provenance downgrade: absence of authority evidence is being treated
as evidence of independent authority.

## Frozen attack

Construct decisive, otherwise production-valid bundles whose manifest and
executable came from the target repository. Compare:

1. correctly labelled `repository_supplied` bundles;
2. the same bundles after deleting `verification_authority` from serialized
   JSON;
3. explicitly labelled `auto_planned` positive controls.

Sweep 128 downgrade attacks and 32 positive controls across `VERIFIED`,
`PARTIALLY_VERIFIED`, and `CONTRADICTED` raw verdicts.

## Predicted correction

- The publication gate accepts a decisive result only when authority is
  explicitly `auto_planned`.
- Missing authority fails closed while retaining the raw verdict and numeric
  observations as provisional evidence.
- The hosted auto-verification path stamps every primary and additional bundle
  `auto_planned` before gating.
- The hosted repository-spec path continues to stamp `repository_supplied`.
- The service callback validates that every bundle authority matches its job
  mode, preventing an authenticated but malformed worker result from crossing
  the boundary.

## Kill criteria

Kill or reformulate if any missing-authority attack remains definitive, if a
repository-spec bundle can claim `auto_planned`, or if correctly stamped
auto-planned controls lose decisive verdicts under otherwise valid runtime
provenance.

## Claim boundary

This does not prove that automatic planning is scientifically independent or
correct. It closes one concrete fail-open downgrade in authority provenance.
