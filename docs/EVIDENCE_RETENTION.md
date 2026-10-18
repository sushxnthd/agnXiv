# Evidence Retention Policy

AgnXiv evidence is split into durable control-plane records and short-lived execution artifacts.

## Durable records

The production PostgreSQL database retains job metadata, result JSON, signed verification statements, DSSE envelopes, and the tamper-evident transparency receipt for the lifetime of the service unless a documented legal or privacy deletion requirement applies. Transparency receipts contain hashes and non-secret job identifiers rather than raw research outputs.

The transparency chain is append-only at the application layer. Every terminal job state is atomically committed with a receipt containing the terminal payload digest, previous receipt hash, sequence number, status, and timestamp. `GET /v1/transparency` exposes the receipt chain independently of GitHub issue rendering.

## Ephemeral execution artifacts

GitHub Actions artifacts are transport/debugging material, not the system of record. Hosted worker result artifacts should be retained only long enough for callback delivery and incident diagnosis. Benchmark and release-gate artifacts may be retained longer for engineering auditability.

Raw unpublished datasets, model checkpoints, repository workspaces, and temporary container files are not retained by the hosted verifier after the ephemeral runner exits unless a future product mode explicitly establishes a separate storage contract.

## Deletion

Deleting or redacting a durable evidence payload must not silently rewrite the transparency history. If a legal/privacy deletion is required, the service should remove the protected payload while retaining a non-sensitive tombstone and its original digest whenever legally permitted.

## Backups

Production PostgreSQL backups must include both job tables and transparency tables. A restore is not accepted until the restored database passes the full transparency-chain verification endpoint.
