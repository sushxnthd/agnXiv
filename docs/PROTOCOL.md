# AgnXiv Verification Protocol

## Principle

AgnXiv does not certify that a scientific paper is universally true.

It issues narrower, replayable statements about exact versions of claims and
artifacts.

## Verification layers

### V0 — Artifact Bound

The exact manuscript, code, data and environment are content-identified.

### V1 — Executable

The declared computational workflow completes in a clean, isolated environment.

### V2 — Claim Reproduced

A reported claim is mapped to an observation produced by execution and the
observation satisfies a declared comparison policy.

### V3 — Robustness Tested

A V2 claim is challenged under a declared set of perturbations or repeated
conditions and the complete outcomes are reported.

### V4 — Independently Reimplemented

The principal method is implemented independently from the manuscript
description and the result is tested without relying on the authors'
implementation.

### V5 — Independently Replicated

Independent data or physical/experimental evidence supports the finding. This
level is domain dependent and often cannot be automated.

## Verdicts

Each claim receives one of:

- VERIFIED
- PARTIALLY_VERIFIED
- CONTRADICTED
- UNABLE_TO_VERIFY

UNABLE_TO_VERIFY is a normal safety outcome.

## Separation of concerns

AgnXiv keeps these concepts separate:

- reproducibility;
- robustness;
- methodological validity;
- novelty;
- scientific importance;
- editorial publishability.

Only evidence actually tested by the protocol may carry a verification claim.

## Version binding

A verification applies to exact artifact contents. A new manuscript, code,
dataset or environment version requires a new attestation.

## Replayability

A public verification record should contain enough provenance for an
independent verifier to replay the declared test: artifact identifiers, runtime
identity, command, policy, raw-output hashes and verdict.

## Core trust metric

Coverage is useful. False passes are dangerous.

AgnXiv optimizes for a low false-pass rate and may abstain when evidence is
ambiguous.
