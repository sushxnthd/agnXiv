# Multi-region strategy and disaster recovery

AgnXiv treats the hosted control plane as stateless except for PostgreSQL and
the signing key material. Untrusted research execution is delegated to
ephemeral GitHub-hosted worker VMs, so execution workers are replaceable and
do not carry durable state.

## Production topology

A production deployment should use:

- a primary control-plane region;
- a geographically separate recovery region with the same service image and
  configuration contract;
- PostgreSQL backup/replication material that can be restored independently of
  the primary region;
- the same public issuer key history in both regions, with active private key
  material supplied by the deployment secret manager;
- DNS or edge routing capable of moving traffic to the recovery region.

The control plane never relies on local worker state. Jobs are content-bound to
a Git commit, and stale in-flight jobs are failed rather than silently resumed
after a regional outage. Clients can safely retry creation with the same
Idempotency-Key.

## Recovery objectives

The repository-level disaster-recovery contract is:

- **RPO:** the most recent completed PostgreSQL backup/replication point;
- **RTO:** restore database, verify the transparency chain, verify signing-key
  availability, pass /readyz and /v1/ops/status, then move traffic;
- no recovered deployment may report ready if PostgreSQL, issuer keys, or the
  transparency chain fail validation.

## Automated cross-region drill

`.github/workflows/cross-region-recovery-drill.yml` creates two independent
PostgreSQL server processes representing region A and region B. It migrates and
seeds region A, produces a custom-format recovery point, restores it into the
independent region B server, stops region A, and then proves that region B
still has all jobs and a valid transparency chain.

The drill runs on relevant changes, weekly, and on demand. Its artifact contains
the backup and SHA-256 digest used for the failover.

This drill validates the software recovery path and state portability. Actual
geographic placement, DNS failover, managed replication, and secret-manager
replication remain deployment responsibilities and must be exercised by the
infrastructure operator before a specific deployment is declared regionally
redundant.
