# Build-to-execution image binding gate

## Decisive falsification

At pre-fix commit `d43dafab91089d925f4c4a7261c20604ce8cf146`, a
constrained, hash-pinned build recorded the canonical image ID
`sha256:aaaa...aaaa`, while the scientific execution recorded the distinct
canonical ID `sha256:bbbb...bbbb`. The publication gate emitted
`CONTRADICTED`, with no provisional verdict and no blocker.

This falsifies the strongest simple baseline: validating each digest's syntax
does not bind the executed environment to the audited build. Both hosted paths
also invoked execution through `BuildResult.image_ref`, a mutable local tag, so
a retag race remained a direct alternative explanation.

The compact negative witness is preserved in
`research/results/execution-image-binding-pre-fix-witness.json`.

## Enforcement mechanism

The hosted runner now passes `BuildResult.image_id` to both zero-manifest and
verification-spec execution. The sandbox independently resolves that reference
before launch and records the actual image ID in the verification bundle.

At publication, a decisive scientific verdict now requires:

1. a recorded execution summary;
2. a canonical execution image ID; and
3. exact equality between the execution image ID and the audited build image
   ID.

Any failure publishes `UNABLE_TO_VERIFY`, retains the raw numeric decision as
`provisional_verdict`, and preserves expected value, observation and error.

## Frozen evidence

| Gate | Result |
|---|---:|
| Distinct canonical substitution attacks | 128/128 abstained |
| False definitive verdicts | 0 |
| Measurements and provisional decisions preserved | 128/128 |
| Missing execution evidence | abstained |
| Malformed execution ID | abstained |
| Exact build/execution controls | 4/4 decisive |
| Hosted execution paths using immutable ID | 2/2 |
| Independent stdlib-only audit | 128/128 |
| Independent production imports | 0 |
| Full repository regression | 206/206 passed |
| Ruff | clean |

The primary matrix digest is
`272ca143ed9f0087ab519fd81f08b9e5e8aa33edcdf4385e704aa8608c4fc835`.
The independent audit digest is
`c18c8466b5739d87aba21eccbc3ec917c301de8e4312d2dcf211dbae254f482c`.

The production gate runs both the primary verifier and the independent checker
and uploads their compact outputs with the other frozen safety evidence.

## Threat model and direct consequence

The mechanism closes substitution between environment construction and
scientific execution, including accidental tag collision, concurrent retagging
and a compromised intermediate component that supplies a different but
well-formed image ID. The check is made at the independent verdict boundary, so
an upstream caller cannot convert the mismatch into a definitive claim.

Hosted execution no longer depends on the mutable tag after construction. This
turns the recorded execution ID from passive metadata into an authorization
condition for scientific publication.

## Novelty and limits

Content-addressed execution and equality checks are standard supply-chain
security mechanisms, not a new cryptographic construction. The defensible
agnXiv result is their fail-closed application to scientific-claim publication,
with a pre-fix false-pass witness, adversarial valid-digest sweep, independent
checker, measurement-preserving abstention and direct runtime change.

This does not establish registry authenticity, image provenance, image
availability, sandbox isolation, dependency correctness, historical fidelity,
dataset identity, repository semantics or scientific validity. It binds only
the locally audited build content ID to the content ID actually selected for
execution.

## Smallest supported claim

Locally, agnXiv now suppresses definitive hosted scientific verdicts whenever
the recorded execution image is missing, malformed or different from the
audited built image, while preserving all frozen exact-match controls and raw
measurements. Hosted CI must pass on the exact commit before claiming hosted
enforcement.
