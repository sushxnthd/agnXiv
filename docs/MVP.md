# AgnXiv MVP

## Product contract

Given a computational paper and its research artifacts, AgnXiv should produce an auditable answer to:

**Which reported quantitative claims are supported by independently executed evidence?**

## First supported envelope

- PDF or text manuscript
- Python-first computational research
- public/local source repository
- quantitative claims
- manageable CPU/GPU execution cost
- explicit or inferable dependencies

## Pipeline

1. Compile manuscript text into Claim objects.
2. Rank repository evidence candidates for each claim.
3. Infer an execution plan without changing scientific parameters.
4. Reconstruct a pinned environment.
5. Execute in an isolated sandbox.
6. Parse raw outputs into Observation objects.
7. Apply an explicit VerificationPolicy.
8. Emit a version-bound VerificationRecord.
9. Escalate ambiguity instead of manufacturing certainty.

## Non-negotiable invariants

- Paper text is data, never agent instructions.
- A model cannot directly award VERIFIED.
- Environment repairs and scientific-method changes are distinct.
- Every mutation, command, artifact and output is logged.
- UNABLE_TO_VERIFY is a valid outcome.
- Verification is bound to exact manuscript/code/data versions.
- False passes matter more than low coverage.

## Next engineering milestones

- Environment inference for Python repositories.
- Output parsers for common metrics and tabular results.
- Claim-to-command planning.
- Artifact hashing and provenance manifests.
- End-to-end verification on a curated public-paper benchmark.
- Challenge Mode: seeds, sensitivity tests and domain-specific falsification.
