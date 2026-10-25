# Frozen protocol: build-output identity binding

Status: frozen before correction and adversarial execution.

## Precise question

Can agnXiv record and execute an image that was not the output of its audited
environment build when the deterministic environment tag is reassigned after
`docker build` succeeds but before agnXiv inspects that tag?

## Observed counterexample

The current builder runs `docker build --tag <environment-tag> ...` and then
calls `docker image inspect <environment-tag>` to discover the immutable image
ID. A concurrent actor can retag the name from the genuine build output `A` to
an unrelated local image `B` in that gap. The later build-to-execution gate is
internally consistent because both the recorded build ID and execution ID are
`B`, while the build plan and logs still describe `A`.

## Proposed enforcement

1. Pass Docker an `--iidfile` outside the build context.
2. Read the canonical SHA-256 image ID written by the build operation itself.
3. Reject missing, malformed, non-canonical, or multiply populated identity
   evidence.
4. Continue tagging the image for operator convenience, but never use the tag
   lookup as the scientific provenance identity.
5. Execute and publish only the immutable ID returned through the iidfile.

## Frozen gates

- At least 128 tag-substitution schedules; the old inspect-after-build baseline
  must accept every substitution and the iidfile mechanism must bind every case
  to the genuine output.
- Missing, empty, malformed, and non-canonical iidfiles must fail closed.
- At least 16 unchanged controls must preserve exact output identity.
- Independent stdlib-only checker with zero production imports.
- Full regression, deterministic evidence, Ruff, diff check, and hosted CI.

## Smallest supported claim

The correction may claim only that agnXiv derives a successful environment
build's scientific provenance identity from Docker's build output rather than a
subsequent mutable-tag lookup. It does not establish Docker-daemon integrity,
builder correctness, image safety, registry authenticity, dependency fidelity,
sandbox isolation, or scientific validity.
