# Dependency-manifest snapshot binding protocol

Status: frozen before adversarial execution.

## Precise question

Can agnXiv publish a decisive hosted verdict when the dependency manifest changes
after its digest is recorded in the build plan but before Docker receives the build
context?

## Threat model

The research checkout may be mutated concurrently by an untrusted workflow step,
hook, or repository process. The Docker daemon and agnXiv process are trusted; host
compromise is out of scope.

## Existing baseline

`plan_python_environment` records SHA-256 and precision from the repository
manifest. `build_python_environment` later resolves the base image and only then
copies the manifest into a temporary Docker context.

## Frozen attack sweep

For 128 deterministic trials, start from a distinct fully hash-pinned manifest A.
At the first base-image identity inspection, replace it with a distinct fully
hash-pinned manifest B. Capture the bytes presented to Docker.

A false pass occurs if all hold:

1. the serialized build plan records SHA-256(A);
2. Docker receives B;
3. the build returns canonical base and environment image IDs; and
4. `gate_hosted_verdict` leaves a provisional decisive verdict decisive.

## Candidate enforcement

Copy the manifest into the private build context and verify that the copied bytes
still match the frozen plan digest before invoking Docker. On mismatch, abort with
`EnvironmentBuildError`. The Docker context, not the mutable repository path,
then becomes the sole build input.

## Controls and gates

- 128/128 A→B races must fail before Docker.
- 16/16 unchanged-manifest controls must still build.
- No decisive verdict may survive a mismatched recorded and built manifest.
- An independent checker must reproduce the boundary without importing production
  code.
- Full tests, Ruff, deterministic evidence rerun, and hosted workflows must pass.

## Claim boundary

This tests repository-manifest TOCTOU during one build. It does not establish
package-index authenticity, base-image security, host integrity, historical
fidelity, or scientific validity.
