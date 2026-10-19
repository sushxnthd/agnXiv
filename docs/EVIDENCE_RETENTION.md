# Evidence retention and durable archives

AgnXiv treats the verification record itself as durable scientific evidence.

## What is archived

Every completed verification result creates exactly one
`agnxiv.evidence-capsule/1` record in PostgreSQL in the same transaction as
its transparency-ledger entry. The capsule contains:

- job identifier and verification mode;
- pinned Git repository and commit;
- versioned arXiv identifier when present;
- normalized DOI and publisher-registry binding when supplied;
- the complete hosted verification result, including signed in-toto Statement
  and DSSE envelope when signing is configured;
- the transparency sequence, entry hash, and result commitment.

The capsule is serialized canonically and identified by SHA-256.

## Immutability

The `agnxiv_evidence_archives` table is append-only. PostgreSQL and SQLite
database triggers reject UPDATE and DELETE operations. A verification archive
therefore cannot be silently rewritten after publication.

The public endpoint
`GET /v1/evidence/{job_id}/commitment` exposes the capsule SHA-256,
transparency binding, retention deadline, pinned public source identifiers, and
publication-registry metadata. The complete capsule is available through the
API-key-protected `GET /v1/jobs/{job_id}/evidence` endpoint.

## Retention policy

Public verification evidence capsules have a **minimum retention period of 10
years**. AgnXiv currently has no automatic deletion path, so archives are
effectively retained beyond that deadline unless a deliberate future migration
introduces a reviewed disposal process.

The stored `retain_until` timestamp is at least 3,653 days after creation,
covering a full ten-year calendar interval including leap years.

## Backup and disaster recovery

Evidence archives live in the same PostgreSQL durability boundary as jobs and
the transparency ledger. Both recovery workflows verify archive integrity:

- the PostgreSQL backup/restore drill compares the evidence-capsule digest
  before backup and after restore;
- the cross-region drill compares all seeded evidence-capsule digests after
  restoring into an independent secondary PostgreSQL instance and stopping the
  primary.

## Scope boundary

AgnXiv preserves the **verification evidence capsule**, not an unlimited copy
of every third-party dataset, checkpoint, or public repository. Large external
scientific inputs remain content-bound by immutable Git commits, versioned
preprint identifiers, declared artifact digests, and DOI registry records.

This distinction is intentional: AgnXiv guarantees long-term preservation of
what it asserted and the cryptographic identities of what it used. It does not
claim archival custody of arbitrary third-party scientific data unless that
data is separately deposited in a durable repository.
