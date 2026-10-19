# Sandbox security and operations hardening — 2026-10-19

## Passed controls

- Ephemeral outer worker boundary workflow: PASS.
- Full repository tests after boundary enforcement: PASS.
- Production safety gate after boundary enforcement: PASS.
- Security audit after boundary enforcement: PASS.
- Operational SLO contract workflow: PASS.
- Existing PostgreSQL recovery drill: PASS.
- Independent-instance cross-region recovery drill: PASS.
- Service-image and external benchmark regressions on the hardening branch: PASS.

## Security boundary

Untrusted research code is now bounded by a no-network/non-root/read-only
container inside a fresh GitHub-hosted VM. The execution job is denied OIDC and
AgnXiv service credentials; the OIDC-enabled callback remains a separate job.

## Operations

The control plane exposes an authenticated fail-closed SLO endpoint and a
scheduled production watcher. Recovery is validated across independent
PostgreSQL server instances with primary shutdown before secondary validation.

## Residual external requirement

Automated security review is not a substitute for an independent human
penetration test. The human/external review remains explicitly uncompleted and
must be performed before private-artifact handling or a larger untrusted-workload
risk envelope.
