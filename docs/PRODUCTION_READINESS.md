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
- [x] Held-out false-pass validation includes at least 299 distinct external paper-level negative-control clusters with zero false passes and a one-sided 95% upper bound <=1%. Current external ReproRepo-seeded result: 308 clusters, 0 false passes, upper bound 0.9679% (`research/results/external-false-pass-v1-2026-10-19.md`).
- [x] Central-claim routing is validated beyond the small v0 diagnostic set on 86 disjoint held-out papers from two external metadata sources. Aggregate Recall@3 = 98.84% and Recall@5 = 100% against frozen author-metadata gold, exceeding the predeclared n >= 75, R@3 >= 90%, R@5 >= 95% gate (`research/results/centrality-production-v1-2026-10-19.md`).
- [x] Historical environment recovery reaches the predeclared production threshold on a fresh disjoint SciCoQA slice: dependency-source classification 30/31 = 96.77% and dependency-only environment construction 7/8 = 87.5%, exceeding the >=95% classification and >=75% build-success gates (`research/results/historical-environment-v1-2026-10-19.md`).

### Execution security

- [x] Research execution is separated from the control plane.
- [x] Research containers run non-root with private IPC, without network, added Linux capabilities, or write access to host evidence.
- [x] GitHub credentials are not persisted into research execution.
- [x] Worker callbacks require GitHub Actions OIDC.
- [x] Returned Git commit must match the control-plane pinned commit.
- [x] Dependency installers do not receive the research source tree.
- [x] Hosted research execution has a dedicated outer VM boundary: each execution job runs on a fresh GitHub-hosted VM, while untrusted code runs in a no-network, non-root, read-only Docker sandbox. The execution job is regression-tested to have no OIDC token access or AgnXiv service credentials (`.github/workflows/sandbox-boundary.yml`).
- [x] Continuous Python dependency vulnerability scanning with a blocking `pip-audit` gate and CycloneDX SBOM output.
- [x] Static security analysis gates cover Python source with Bandit and GitHub Actions with zizmor.
- [x] Container/OS package vulnerability scanning blocks HIGH/CRITICAL findings in the hosted service image.
- [x] Threat-model review and external automated security analysis are release gates: Bandit, zizmor, Trivy, pip-audit/SBOM, and GitHub CodeQL security-extended queries (`docs/SECURITY_REVIEW.md`).
- [ ] Independent human penetration/security review before accepting private artifacts or expanding beyond the public-beta risk envelope.

### Control-plane reliability

- [x] PostgreSQL is required for production readiness.
- [x] High-entropy API keys are required for readiness.
- [x] HTTPS public URL and HTTPS OIDC audience are required.
- [x] Signing key must be configured and cryptographically parseable.
- [x] Stale jobs are failed automatically so lost callbacks cannot permanently consume quota.
- [x] Active-job and hourly quotas exist.
- [x] Liveness and strict readiness endpoints exist.
- [x] Capability metadata endpoint exposes the supported API contract without secrets.
- [x] Idempotency keys for job creation, with database uniqueness and conflicting-request rejection.
- [x] Authenticated operator job metrics and request correlation IDs.
- [x] Authenticated operational SLO evaluation (`/v1/ops/status`) checks database reachability, transparency-chain integrity, active-job age/capacity, and stale-callback error budget; `.github/workflows/ops-slo-monitor.yml` runs the contract in CI and can poll production every 15 minutes when `AGNXIV_PRODUCTION_URL` and `AGNXIV_MONITOR_API_KEY` are configured.
- [x] Backup/restore drill for PostgreSQL runs in CI and weekly, verifies restored job data and transparency-chain integrity, and confirms append-only database guards survive restoration.
- [x] Key rotation procedure and issuer-key rollover metadata, including active/retired/revoked Ed25519 key discovery and fail-closed keyring validation (see `docs/KEY_ROTATION.md`).
- [x] Multi-region recovery strategy is documented and an independent-instance failover drill runs in CI/weekly: region A is backed up, restored into an independent region B PostgreSQL server, region A is stopped, and region B must retain all jobs plus a valid transparency chain (`docs/DISASTER_RECOVERY.md`, `.github/workflows/cross-region-recovery-drill.yml`).

### Evidence durability

- [x] Git commit, manuscript, artifacts, runtime identity, output digests, and locator are recorded.
- [x] Verification statements can be signed with DSSE/Ed25519.
- [x] Living Attempt → Record → Challenge model exists.
- [x] Independence-aware claim aggregation exists with regression coverage.
- [x] Append-only database-backed transparency log independent of GitHub issue availability, with deterministic result commitments, hash chaining, public read endpoints, and database mutation guards.
- [ ] Long-term artifact retention policy.
- [ ] DOI/publisher registry integration.

## Evidence grades

Raw verifier verdicts and scientific evidence strength are deliberately separate.

**STRONG** means a decided numeric result used an explicit locator, clean execution, immutable evidence, and a base-only/locked/version/hash-pinned dependency environment.

**CONDITIONAL** means the numeric comparison executed cleanly with an explicit locator, but the reconstructed dependency environment is not strong enough to claim publication-era equivalence.

**INCONCLUSIVE** covers missing execution integrity, ambiguous/fallback observation semantics, or no decided numeric verdict.

A CONDITIONAL CONTRADICTED result is therefore a measured divergence in the executed reconstructed environment, not a strong paper-level falsification claim.

## Release rule

Do not replace a failed P0 safety gate with a looser threshold merely to improve verification coverage. Production coverage is subordinate to selective correctness.
