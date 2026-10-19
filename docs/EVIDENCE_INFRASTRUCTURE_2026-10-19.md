# Evidence infrastructure completion — 2026-10-19

AgnXiv's repository-level evidence-durability infrastructure is complete.

## Durable evidence capsules

Each completed verification now creates one
`agnxiv.evidence-capsule/1` record transactionally with its transparency entry.

Properties:

- canonical JSON payload;
- SHA-256 content address;
- append-only PostgreSQL/SQLite mutation guards;
- transparency sequence and entry-hash binding;
- pinned Git repository/commit and versioned arXiv identifier;
- DOI/publication registry binding when supplied;
- complete hosted result, including statement and DSSE envelope when signing is
  configured;
- minimum retention deadline of 3,653 days;
- no automatic deletion path.

The public commitment endpoint exposes the archive digest, transparency binding,
retention policy, public source identifiers, and publication identity. Full
capsules require the owning API key.

## Recovery evidence

Both PostgreSQL recovery paths validate archive content hashes:

- ordinary backup/restore compares the pre-backup and restored evidence digest;
- cross-region recovery compares seeded capsule digests after restoring into an
  independent secondary PostgreSQL server and stopping the primary.

Both drills passed on the evidence branch.

## DOI and publisher/research-object registries

A DOI-bearing job is normalized locally, then resolved against:

1. Crossref;
2. DataCite fallback.

The returned DOI must exactly match the requested normalized DOI. AgnXiv records
the registry, title/publisher/type/date/URL metadata available from that record,
retrieval timestamp, and SHA-256 of the canonical registry payload.

The publication binding is injected into every verification bundle before
statement generation, so the bundle digest, in-toto Statement, and DSSE
signature cover the registry identity.

A scheduled live integration workflow successfully resolves real official
example records through both Crossref and DataCite, in addition to adversarial
offline unit tests for mismatched DOI rejection.

## Scope boundary

Long-term retention applies to AgnXiv's verification evidence capsule. AgnXiv
does not claim custodial preservation of unlimited third-party datasets,
checkpoints, repositories, or publisher PDFs. Those external inputs remain
bound by content hashes, immutable Git commits, versioned preprint identifiers,
and publication-registry records, and can be deposited separately in archival
repositories when long-term byte custody is required.
