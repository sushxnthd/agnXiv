# Frozen protocol: build-to-execution image binding

## Question

Can a hosted scientific verdict remain decisive when the container image that
actually executed differs from the image produced by the audited environment
build, even though both image identifiers independently have canonical Docker
SHA-256 syntax?

## Pre-implementation falsification

Construct a constrained, hash-pinned positive control whose `BuildResult`
records built image ID `sha256:aaaa...aaaa` and whose execution summary records
the same ID. Then replace only the execution image ID with a distinct canonical
ID `sha256:bbbb...bbbb`.

The current publication gate checks the syntax of the built and base image IDs,
but does not compare the execution summary to the build result. The frozen
prediction is therefore that the substituted execution still receives a
definitive verdict before correction.

This models a mutable-tag race between environment construction and scientific
execution. The runtime already resolves and records the actual image ID before
launch, so the attack needs no trusted-registry assumptions and can be decided
from existing evidence.

## Required correction

1. Hosted execution must be invoked by the immutable built image ID, not the
   mutable local tag.
2. The publication boundary must require an execution summary.
3. The execution image ID must be canonical and exactly equal to the audited
   built image ID.
4. Failure must publish `UNABLE_TO_VERIFY` while preserving the measurement and
   provisional verdict.
5. Existing non-decisive verdicts must remain stable.

## Frozen sweep

- distinct canonical build/execution IDs, varying one nibble at all 64 digest
  positions and in both directions;
- malformed execution IDs already covered by the canonical grammar boundary;
- missing execution evidence;
- exact-match controls for multiple canonical IDs;
- strongest simple baseline: syntax validation alone.

## Success threshold

- 128/128 distinct-canonical substitution attacks abstain;
- zero false definitive verdicts;
- all measurements and provisional decisions survive;
- missing and malformed execution evidence abstains;
- exact-match controls remain decisive;
- an independent standard-library checker reproduces the matrix without
  importing production code;
- both hosted execution paths pass immutable IDs to the sandbox;
- full regression and the production gate pass.

## Smallest possible claim

If the gate passes, agnXiv can claim only that a decisive hosted verdict is
cryptographically bound to the exact local image content ID recorded by both
environment construction and execution. This does not establish image origin,
registry authenticity, sandbox isolation, dependency correctness, historical
fidelity, or scientific validity.
