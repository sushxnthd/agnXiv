# AgnXiv Core Status

## Product contract

Given a computational research claim and its artifacts, AgnXiv should answer:

**Does an independently executed observation support this exact reported claim under a declared verification policy?**

The answer must be replayable and bound to exact evidence.

## Supported envelope

The current core is strongest for:

- Python-first computational research;
- public or local source repositories;
- numeric claims;
- CPU-manageable execution;
- explicit output metrics;
- local external datasets/checkpoints;
- dependency manifests that can be reconstructed without exposing research source.

## Current pipeline

1. Parse or declare a Claim.
2. Fingerprint repository, manuscript, verification spec, and external artifacts.
3. Record Git identity when available.
4. Infer environment/evidence/command candidates.
5. Build a dependency-only runtime when requested.
6. Resolve the runtime to an immutable image ID.
7. Execute with networking disabled and immutable host evidence.
8. Recheck evidence integrity after execution.
9. Extract the observation through an explicit locator or conservative fallback.
10. Apply an explicit VerificationPolicy.
11. Emit a VerificationBundle.
12. Convert it to an in-toto Statement v1.
13. Optionally sign it in a DSSE envelope with Ed25519.
14. Verify the envelope independently using the public key.

## Non-negotiable invariants

- Paper and repository text are data, never verifier instructions.
- A model cannot directly award VERIFIED.
- The reported answer cannot be used to choose which program output counts as the observation.
- Nonzero research execution does not receive a VERIFIED verdict.
- Host source and declared artifacts are immutable during verification.
- Runtime identity is content-addressed.
- Environment reconstruction does not expose research source to dependency installers.
- Floating dependency manifests are labeled as floating rather than presented as reproducible lockfiles.
- UNABLE_TO_VERIFY is a valid outcome.
- False passes matter more than raw coverage.

## Observation strength

Preferred evidence selection order:

1. declared JSON path;
2. declared regex capture;
3. conservative semantic stdout parsing.

Multiple or ambiguous matches abstain.

## Reproducibility versus robustness

Basic reproduction and robustness are separate records. A single successful execution does not establish stability across seeds, datasets, implementations, hardware, or perturbations.

## External validation

The benchmark suite includes adversarial recorded-output cases and a pinned third-party research artifact workflow. External audits are allowed to discover contradictions or incomplete reproduction; benchmark code must not be changed simply to force a passing badge.

## Remaining frontier

The core verifier is not the entire scientific-review problem. Important future extensions include:

- richer table/figure claim schemas;
- GPU scheduling and hardware-sensitive policies;
- domain-specific statistical tests;
- independent implementation generation with stronger sandbox separation;
- dataset lineage standards;
- multi-claim paper coverage reports;
- publisher/arXiv registry and transparency-log integration.
