# AgnXiv

**AgnXiv turns computational research claims into executable, content-bound verification records.**

The core contract is deliberately narrower than peer review:

> **exact claim + exact source/data/runtime + declared test → replayable verdict + signed provenance**

AgnXiv does **not** certify that a paper is universally true, novel, important, or publishable. It certifies specific computational claims under explicit evidence and policies.

## Public product

AgnXiv's public beta is a standalone GitHub Pages product:

https://sushxnthd.github.io/agnXiv/

The user-facing flow is:

1. Open the AgnXiv verifier.
2. Paste an arXiv paper and public GitHub repository, or choose an existing `agnxiv.json` manifest.
3. AgnXiv validates and prepares the request inside the product UI.
4. GitHub appears only for the final authenticated confirmation because GitHub Pages cannot create repository issues anonymously without exposing credentials.
5. GitHub Actions runs the trusted AgnXiv worker on an ephemeral hosted runner.
6. Results are rendered back on a dedicated AgnXiv verification-record page; the underlying issue and Actions run remain the public provenance layer.

Direct verifier: https://sushxnthd.github.io/agnXiv/verify.html

The repository Issue Form remains available as a fallback submission route.

### Manifest-free scientific verification

The default **Auto-verify** flow now accepts only a versioned arXiv paper and a public pinned GitHub repository. When planning, dependencies, files, and workflow ordering are safe enough, it builds a dependency-only runtime and executes the documented command without network access. Locator discovery is blinded to the paper's reported numerical result; it freezes a unique, labeled stdout metric selector and digest **before** running claim comparison. AgnXiv then executes the workflow again with the frozen selector and emits provenance-bound **claim-level** verdicts. If prerequisites or selectors are ambiguous, it returns `needs_review` without certifying the paper.

**External integration case:** `arXiv:2604.15702`, `synthiumjp/metacognitive-monitoring-battery@2f83d0fa506e7af2b72ca191b65ce42e07c9e185`. The no-manifest runner recomputed two reported reliability statistics: split-half `0.504` versus `0.51` and Spearman–Brown `0.67` versus `0.68`. Under the predeclared 1% relative tolerance, both received a narrow `CONTRADICTED` claim-level verdict. These are small numeric differences, not assessments of the overall paper or its authors. Results depend on the reconstructed runtime, and floating dependencies do not guarantee publication-era equivalence. The full pinned Docker-backed public CI evidence is in `.github/workflows/zero-manifest-real-paper.yml`.

**Known limitations:** Only uniquely mapped numeric stdout metrics can be verified automatically in this phase. A workflow that runs successfully without a trustworthy locator still abstains; publication novelty, significance, and full scientific validity remain outside AgnXiv's scope. The result is an integration demonstration, not a statistically representative false-pass measurement.

## Evidence network beta

AgnXiv now treats verification as a living evidence network rather than a one-shot badge:

- **Lookup** — search an arXiv paper before trusting, citing, or reproducing it.
- **Attempt** (`agnxiv.attempt/1`) — one durable reproduction or verification attempt, including blocked and inconclusive attempts.
- **Record** (`agnxiv.record/1`) — the aggregate evidence state of one paper across attempts and challenges.
- **Challenge** (`agnxiv.challenge/1`) — an evidence-specific result divergence with a public response thread and machine-readable provenance.

Public evidence states intentionally differ from low-level verifier verdicts:

- **REPRODUCED** — an executed observation satisfied the declared claim policy.
- **PARTIALLY_REPRODUCED** — only a declared subset was supported.
- **RESULT_DIVERGENCE** — an executed observation differed under the declared test; this is not an allegation of misconduct or universal falsity.
- **EVIDENCE_INCOMPLETE** — AgnXiv could not safely proceed because the evidence chain or execution semantics remained ambiguous.
- **EXECUTION_BLOCKED** — the declared attempt could not execute reliably.
- **INCONCLUSIVE** — available evidence does not support a stronger state.

Raw verifier verdicts remain preserved in provenance. AgnXiv does not collapse a paper into a universal truth score.

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
