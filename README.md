# AgnXiv

**AgnXiv turns computational research claims into executable, content-bound verification records.**

The core contract is deliberately narrower than peer review:

> **exact claim + exact source/data/runtime + declared test → replayable verdict + signed provenance**

AgnXiv does **not** certify that a paper is universally true, novel, important, or publishable. It certifies specific computational claims under explicit evidence and policies.

## What is implemented

AgnXiv currently supports:

- quantitative claim extraction from text/PDF;
- repository evidence and command discovery;
- deterministic absolute, relative, lower-bound, and upper-bound policies;
- explicit JSON-path and regex result locators;
- conservative semantic stdout parsing as a fallback;
- source, manuscript, verification-spec, dataset, and checkpoint hashing;
- Git commit / dirty-state provenance when available;
- isolated Docker execution with no network, no added capabilities, resource limits, and immutable host evidence;
- manifest-only Python environment construction;
- dependency pinning classification: base-only, floating, version-pinned, or hash-pinned;
- repeated-run robustness assessment kept separate from reproduction;
- adversarial false-pass benchmarks;
- in-toto Statement v1 output;
- DSSE + Ed25519 signing and offline signature verification;
- declarative versioned verification manifests.

## Verdicts

- **VERIFIED** — the executed observation satisfies the declared policy.
- **CONTRADICTED** — the executed observation violates the declared policy.
- **UNABLE_TO_VERIFY** — execution, evidence integrity, or observation selection is insufficient for a reliable verdict.
- **PARTIALLY_VERIFIED** — reserved for composite verification where only a declared subset is supported.

Abstention is a normal safety outcome. AgnXiv is designed to prefer missed coverage over false passes.

## Trust model

Models or heuristics may suggest claims, files, commands, or tests. They do not award a verdict.

A numeric verdict is produced only after:

1. the evidence is fingerprinted;
2. the runtime image is resolved to an immutable local image ID;
3. the command executes in the sandbox;
4. source and external artifacts are checked again for mutation;
5. an observation is selected without using the paper's reported value as an answer hint;
6. an explicit policy evaluates that observation.

The strongest observation path is a predeclared structured locator. Current order of preference:

1. **explicit JSON path**;
2. **explicit regex capture**;
3. **conservative semantic stdout parsing**.

## Quick start

Install:

    python -m pip install -e ".[pdf,sign]"
    agnxiv --help

Build a dependency-only runtime without exposing the research source to package installers:

    docker pull python:3.11-slim
    agnxiv build-env ./paper-repo --base-image python:3.11-slim

Verify one explicit claim:

    agnxiv verify-command ./paper-repo       --image agnxiv-env:<plan-id>       --cmd python       --cmd reproduce.py       --expected 0.914       --metric accuracy       --json-path metrics.accuracy

For a portable workflow, ship a versioned manifest and replay it directly:

    agnxiv verify-spec agnxiv.json

A versioned manifest declares the repository, claim, policy, runtime command, optional manuscript/artifacts, and observation locator. The manifest itself is hashed into the verification bundle.

## Signed attestations

Generate an issuer keypair:

    agnxiv keygen       --private-out issuer-private.pem       --public-out issuer-public.pem

A verification can be signed with:

    agnxiv verify-spec agnxiv.json       --sign-key issuer-private.pem       > verification.json

The DSSE envelope can be verified offline with:

    agnxiv verify-envelope envelope.json       --public-key issuer-public.pem

The signed in-toto statement can bind:

- verification-spec SHA-256;
- repository tree SHA-256;
- Git commit and dirty state;
- manuscript SHA-256;
- external artifact SHA-256 values;
- immutable runtime image ID;
- command;
- stdout/stderr digests;
- verification policy;
- observation method and locator;
- final verdict.

## Verification levels

AgnXiv distinguishes progressively stronger evidence:

- **V0 — Artifact Bound:** exact inputs are content-identified.
- **V1 — Executable:** declared workflow completes in isolation.
- **V2 — Claim Reproduced:** an executed result satisfies the declared claim policy.
- **V3 — Robustness Tested:** repeated or perturbed runs satisfy a declared robustness test.
- **V4 — Independently Reimplemented:** the result survives a separate implementation.
- **V5 — Independently Replicated:** independent data or experimental evidence supports the finding.

Higher levels are not inferred from lower ones.

## Development

    python -m pip install -e ".[dev,pdf]"
    ruff check src tests examples/fixture-paper
    pytest

CI runs a full Docker integration path that hashes the manuscript and external artifact, executes structured verification, emits an in-toto statement, signs it with Ed25519, and verifies the DSSE envelope offline.

A separate pinned third-party benchmark is used to test the verifier against research artifacts AgnXiv did not author.

## Core principle

**Discovery can be probabilistic. Verification must be evidence-bound.**
