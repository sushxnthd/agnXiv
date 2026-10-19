# AgnXiv Production Readiness

Production grade means the system remains scientifically conservative and operationally recoverable under failures. A green demo is not enough.

## P0 launch gates

All P0 items must be true before calling the hosted service production-grade.

### Scientific safety

- [x] Reported numeric values do not influence zero-manifest locator selection.
- [x] Ambiguous locators abstain.
- [x] Non-zero research execution cannot receive a positive numeric verdict.
- [x] Host source and external artifacts are mutation-checked.
- [x] RedBench has a zero-false-pass regression gate.
- [x] Floating/unreconstructed dependency environments are labeled **CONDITIONAL** evidence rather than silently treated as publication-era equivalence.
- [x] Multiple claim bundles from one run are preserved.
- [x] Repeated attempts sharing the same evidence cluster are not counted as independent votes.
- [ ] Held-out benchmark includes at least 299 independent SUPPORTS decisions with zero false passes, or otherwise achieves a one-sided 95% false-pass upper bound <=1%.
- [ ] Central-claim selection is validated beyond the small v0 diagnostic set.
- [ ] Historical environment recovery benchmark reaches a predeclared production threshold.

### Execution security

- [x] Research execution is separated from the control plane.
- [x] Research containers run without network, added Linux capabilities, or write access to host evidence.
- [x] GitHub credentials are not persisted into research execution.
- [x] Worker callbacks require GitHub Actions OIDC with a per-job audience, immutable release-tag ref, and exact trusted workflow commit SHA.
- [x] Returned Git commit must match the control-plane pinned commit.
- [x] Dependency installers do not receive the research source tree.
- [ ] Dedicated sandbox provider / microVM boundary for workloads beyond public beta risk envelope.
- [x] Continuous Python dependency vulnerability scanning with a blocking `pip-audit` gate and CycloneDX SBOM output.
- [x] Blocking Bandit static analysis for Python and zizmor analysis for GitHub Actions workflows.
- [x] Container/OS and Python-library vulnerability scanning blocks fixed HIGH/CRITICAL findings in the production image.
- [ ] External security review and threat-model review.

### Control-plane reliability

- [x] PostgreSQL is required for production readiness.
- [x] High-entropy API keys are required for readiness.
- [x] HTTPS public URL and HTTPS OIDC audience are required.
- [x] Signing key must be configured and cryptographically parseable.
- [x] Stale jobs are failed automatically so lost callbacks cannot permanently consume quota.
- [x] Hosted Actions always executes a terminal callback; worker/bootstrap failure synthesizes a fail-closed terminal result instead of waiting for the stale reaper.
- [x] Active-job and hourly quotas exist.
- [x] Liveness and strict readiness endpoints exist.
- [x] Capability metadata endpoint exposes the supported API contract without secrets.
- [x] Idempotency keys for job creation, with database uniqueness and conflicting-request rejection.
- [x] Authenticated operator job metrics and request correlation IDs.
- [x] HTTP request bodies are capped on actual streamed ASGI bytes, including chunked requests without `Content-Length`.
- [x] Production release inputs are bound in a GitHub/Sigstore attested manifest containing commit, service image, base image, dependency lock, trusted workflows, and migrations.
- [x] Fail-closed deployment and rollback runbook requires immutable release tags and matching trusted workflow SHA.
- [x] Error-budget/SLO policy and scheduled synthetic probes exist for the public product and hosted readiness endpoint.
- [ ] Production service URL plus operator notification routing are configured and tested after deployment.
- [x] Scheduled PostgreSQL logical backup/clean-restore rehearsal verifies jobs plus the transparency chain in CI.
- [ ] A restore drill against the actual production database provider and its backup mechanism has been completed.
- [x] Key rotation procedure and issuer-key rollover metadata are implemented; current and retained previous public keys are published by `/v1/issuer`.
- [ ] Multi-region execution strategy and disaster recovery.

### Evidence durability

- [x] Git commit, manuscript, artifacts, runtime identity, output digests, and locator are recorded.
- [x] Verification statements can be signed with DSSE/Ed25519.
- [x] Living Attempt → Record → Challenge model exists.
- [x] Independence-aware claim aggregation exists with regression coverage.
- [x] Hosted job finalization atomically writes a hash-chained, tamper-evident PostgreSQL receipt independent of GitHub issue availability.
- [ ] Transparency history is externally anchored/witnessed so a full database compromise cannot rewrite the entire chain undetectably.
- [x] Long-term evidence and ephemeral execution-artifact retention policy is documented.
- [ ] DOI/publisher registry integration.

## Current launch blockers after production-hardening v2

The repository can now enforce substantially stronger operational invariants, but the hosted service must **not** be called fully production-grade yet. Remaining blockers require evidence or infrastructure outside a code-only CI pass:

1. held-out false-pass evidence at the predeclared confidence bound;
2. broader central-claim and historical-environment validation;
3. a stronger isolation boundary than a shared-kernel Docker container for workloads outside the public-beta envelope;
4. external security/threat-model review;
5. an actual hosted control-plane deployment with alert routing, production-provider restore rehearsal, and disaster-recovery testing;
6. an external transparency witness/anchor.

The connected Railway account currently has no AgnXiv project deployed, so deployment-specific gates cannot yet be truthfully marked complete. `docs/DEPLOYMENT.md` defines the exact release-tag, workflow-SHA, migration, canary, monitoring, backup/restore, and rollback sequence required when a production environment is provisioned.

## Evidence grades

Raw verifier verdicts and scientific evidence strength are deliberately separate.

**STRONG** means a decided numeric result used an explicit locator, clean execution, immutable evidence, and a base-only/locked/version/hash-pinned dependency environment.

**CONDITIONAL** means the numeric comparison executed cleanly with an explicit locator, but the reconstructed dependency environment is not strong enough to claim publication-era equivalence.

**INCONCLUSIVE** covers missing execution integrity, ambiguous/fallback observation semantics, or no decided numeric verdict.

A CONDITIONAL CONTRADICTED result is therefore a measured divergence in the executed reconstructed environment, not a strong paper-level falsification claim.

## Release rule

Do not replace a failed P0 safety gate with a looser threshold merely to improve verification coverage. Production coverage is subordinate to selective correctness.
