# Hosted Service SLO and Incident Policy

These are launch objectives for the AgnXiv control plane. Scientific safety gates are stricter than availability targets and must never be weakened to meet an uptime number.

## Service objectives

For a rolling 30-day production window:

- Control-plane availability: **99.5%** successful responses for `/healthz` and authenticated job submission, excluding planned maintenance.
- Ready-state availability: **99.0%** for `/readyz`. A failed signing key, database, or transparency-chain integrity check intentionally counts as unavailable.
- Hosted dispatch reliability: **>=99%** of accepted jobs either reach a terminal callback or are explicitly failed by the stale-job deadline.
- Evidence integrity: **100%** of terminal hosted jobs receive one transparency receipt.
- Scientific false-pass budget: **0 accepted known false passes**. A suspected false pass is a release-blocking incident, not an error-budget tradeoff.

## Alert conditions

Page/notify an operator when any of the following is observed:

- `/readyz` is non-200 for two consecutive checks;
- active jobs remain above quota for longer than the stale-job deadline;
- stale/failed callback rate exceeds 1% over a 1-hour window;
- transparency-chain verification is invalid;
- signing keyset parsing fails or the current key disappears;
- container or dependency vulnerability gates report a new HIGH/CRITICAL finding;
- any benchmark records a false pass or false contradiction.

## Incident priorities

- **SEV-0 scientific integrity:** possible false verification, evidence mutation, signing-key compromise, or transparency corruption. Stop affected verification/signing paths.
- **SEV-1 security/reliability:** sandbox escape suspicion, callback authentication failure pattern, database outage, or systematic job loss.
- **SEV-2 degradation:** elevated latency, isolated worker failures, or reduced coverage with correct abstention.

Availability recovery never authorizes bypassing sandbox, provenance, locator, signature, or abstention checks.
