# Dependency-manifest snapshot binding result

## Smallest supported claim

agnXiv now fails closed when a selected pip requirements manifest changes after
the build plan records its digest but before Docker receives its build context.
The immutable build context is accepted only when its copied manifest hashes to
the exact digest serialized in the plan.

## Falsified baseline

The previous sequence hashed the repository manifest during planning, resolved
the base image, and then copied the repository path. A concurrent A→B mutation
could therefore produce a build whose plan claimed SHA-256(A) while Docker
installed B. Both A and B could independently satisfy the existing
`hash-pinned` syntax classifier, so canonical image IDs and execution-image
matching did not repair the provenance mismatch.

The frozen sweep constructed 128 distinct pairs of fully hash-pinned manifests.
The old copy-later baseline false-accepted all 128 digest mismatches.

## Enforcement mechanism

`copy_frozen_dependency_manifest` copies the selected manifest into the private
temporary build context and hashes the copied bytes. A mismatch with the frozen
plan digest raises `EnvironmentBuildError` before `docker build` is invoked.
Docker subsequently reads only that private snapshot, not the mutable repository
path.

## Evidence

| Gate | Result |
|---|---:|
| Frozen A→B races | 128/128 rejected before Docker |
| Old-baseline false accepts | 128/128 |
| Unchanged controls | 16/16 built with matching plan/context digests |
| Independent checker | 128/128 attacks and 16/16 controls |
| Independent production imports | 0 |
| Full repository tests | 210/210 passed |
| Ruff | clean |
| Deterministic primary digest | `2bf7b732a18c52a620a44735fcbfbcf9764760fc8d0c6c601a1da8238c332cc4` |
| Independent audit digest | `78fcf9da247b3bffbe1b4558607655f18387dff873a9f907246965ce0777efab` |

Primary evidence is in
`research/results/dependency-manifest-snapshot.json`; the independent transcript
is in `research/results/dependency-manifest-snapshot-audit.json`. The production
gate reruns both generators on every push and pull request.

## Product consequence

A decisive scientific verdict can no longer be authorized by an environment
plan whose dependency digest describes different bytes from those actually
offered to Docker. Drift remains auditable as a controlled build failure rather
than being hidden behind otherwise-valid image identities.

## Limits

This result covers repository-manifest mutation during a single environment
build under a trusted agnXiv process, Docker daemon, and SHA-256 implementation.
It does not establish package-index authenticity, protection against SHA-256
collision, host integrity, base-image security, sandbox isolation, historical
environment fidelity, or correctness of the scientific claim. Network-fetched
artifacts remain governed separately by pip hash checking and the existing
dependency-precision gate.
