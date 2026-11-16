# CLI external-verification release gate

## Product consequence

The release-candidate CLI now exposes the complete narrow workflow that was previously available only through an internal hosted-runner entry point:

1. validate local Git, PDF, Docker CLI, and Docker daemon prerequisites;
2. clone one pinned public GitHub repository;
3. download and hash-check one versioned arXiv manuscript;
4. conservatively plan the documented workflow;
5. construct a dependency-only container runtime;
6. execute without network access against immutable evidence;
7. freeze an explicit observation selector before claim comparison;
8. emit a bounded verdict and export the complete JSON audit record.

Run the readiness check first:

```console
agnxiv doctor
```

Then run the pinned external integration case:

```console
agnxiv verify-external \
  --repository synthiumjp/metacognitive-monitoring-battery \
  --repository-ref 2f83d0fa506e7af2b72ca191b65ce42e07c9e185 \
  --arxiv-id 2604.15702v2 \
  --expected-manuscript-sha256 f60c57f5c39453638b82b8eb1317db6b9e92d440ddf4b06eaab0a6f3a08605a7 \
  --output agnxiv-real-paper-audit.json
```

The output file is created atomically and is never silently overwritten. Setup failures are also exported with exact failing checks and remediation. A scientific `needs_review` outcome exits successfully because conservative abstention is a completed verification workflow, not a process crash.

## Preserved negative result

A clean installation of the public `v0.1.0` wheel succeeded and matched its published SHA-256 `f79c98920b114d97b83eb63176f70606951789e9d9c604f354686cc1e6aa3d80`. Running the documented fixture on a machine without Docker returned an evidence-bound `UNABLE_TO_VERIFY` record whose rationale was `No such file or directory: 'docker'`.

This demonstrates that `v0.1.0` is installable but does **not** yet satisfy the stronger current definition of shipped usability on an arbitrary machine. The release-candidate change makes the prerequisite explicit before repository downloads or scientific execution and provides a stable public command for the real external case.

## Acceptance boundary

The GitHub acceptance workflow runs the command on a clean Ubuntu runner and requires the measured `0.504` observation for the paper's reported `0.51` value, a successful sandboxed execution, pinned repository identity, and the final conservative `UNABLE_TO_VERIFY` verdict caused by insufficient environment fidelity. It uploads the complete audit record.

This gate does not establish broad paper coverage, historical environment equivalence, scientific correctness, a deployed hosted service, or a new public tagged release. The exact-head hosted acceptance, dependency audit, and service-image scan have passed. The next public v0.x tag remains blocked on a successful clean-install release-candidate build, review of the candidate artifacts and commit-bound hash manifest, and an explicit non-automatic release decision.
