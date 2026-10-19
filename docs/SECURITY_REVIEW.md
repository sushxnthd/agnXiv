# Security review record

## Scope

This review covers the hosted control plane, GitHub Actions execution path,
dependency builder, Docker research sandbox, worker callback identity, artifact
mounts, transparency ledger, and recovery workflows.

## Trust boundaries

1. Public paper/repository inputs are untrusted.
2. Dependency installation is untrusted and receives dependency metadata only.
3. Research execution occurs inside a locked-down Docker container.
4. The container itself runs inside a fresh GitHub-hosted VM execution job.
5. The execution job has no OIDC permission and receives no AgnXiv service
   secrets.
6. The callback runs as a separate job and obtains short-lived GitHub OIDC only
   after the execution artifact exists.
7. The control plane accepts callback results only from the configured workflow
   identity and validates the pinned Git commit and verdict/provenance contract.

## Reviewed attack classes

- path traversal and symlink escape;
- malicious dependency manifests and source-install side effects;
- command injection through repository metadata;
- container privilege escalation and host mutation;
- outbound exfiltration from research execution;
- credential theft from execution workers;
- callback forgery/replay;
- stale worker quota exhaustion;
- API idempotency races;
- signing-key misuse and rollover;
- transparency-log mutation;
- backup/restore integrity loss;
- workflow supply-chain drift.

## Automated review gates

The release branch is continuously checked by:

- Bandit high-severity Python static analysis;
- zizmor GitHub Actions security analysis;
- pip-audit on the frozen service dependency set;
- CycloneDX SBOM generation;
- Trivy HIGH/CRITICAL service-image scanning;
- GitHub CodeQL with the `security-extended` Python query suite;
- immutable SHA enforcement for every GitHub Action;
- sandbox-boundary regression tests on a GitHub-hosted runner.

## Residual risk

No automated scanner can establish absence of sandbox escapes or application
logic vulnerabilities. A real independent penetration test / human security
review remains a deployment requirement before accepting private artifacts or
raising the public-beta risk envelope. That requirement must not be represented
as completed by this repository's own automated review.
