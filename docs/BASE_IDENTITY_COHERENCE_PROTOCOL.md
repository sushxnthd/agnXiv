# Base-image identity coherence protocol

Status: frozen before implementation.

## Question

Can a mutable base tag change between the local-ID lookup and repository-digest
lookup so that agnXiv builds from one immutable image while recording another
canonical image ID, yet still permits a definitive scientific verdict?

## Threat model

The Docker daemon and SHA-256 primitives are trusted. A concurrent actor may
retag the already-pulled hosted base image between inspections. The attacker
cannot forge a digest or image ID, modify agnXiv code, or modify the private
build context.

## Frozen attack

For distinct canonical identities A and B, the current order observes:

1. mutable tag ID = A;
2. mutable tag repository digest = B;
3. build uses immutable digest B;
4. mutable tag ID after build = A.

The endpoint equality check passes and the result records base ID A even though
the serialized build plan and actual Dockerfile use B.

Generate 128 deterministic A/B schedules. The matched control keeps one image
throughout. No Docker daemon is required; the checker substitutes only the two
identity-resolution functions and build subprocess.

## Proposed correction

Resolve the repository digest first, then derive the recorded image ID from that
immutable digest reference. The mutable tag may still be inspected after the
build as defense in depth, but it must never supply the audited base identity.

## Gates

- Old split-resolution baseline false-accepts every A-to-B-to-A schedule.
- Corrected implementation never returns an incoherent `(digest B, ID A)` pair.
- All unchanged controls build successfully.
- Missing, malformed, or mismatched immutable identity evidence fails closed.
- An independent standard-library checker imports no production module.
- Full regression, scoped Ruff, diff check, and deterministic evidence rerun
  pass.

## Smallest supported claim

If the gates pass, agnXiv can claim that the base image ID recorded for a hosted
build is derived from the exact immutable repository digest serialized into the
Dockerfile. This does not establish Docker-daemon integrity, registry
authenticity, image safety, dependency correctness, or scientific correctness.

## Kill condition

Kill the kernel if the current code already derives the ID from the immutable
digest, if Docker supplies one atomic primitive already used here, or if the
attack cannot cross the definitive-verdict gate with canonical identities.
