# Transparency roots are now authenticated and freshness-bounded

## Result

The inclusion-only gate accepted all 128 attacks because every case supplied a
mathematically valid Merkle proof against its own asserted root.  The corrected
checkpoint gate produced:

| Gate | Attack false passes | Matched controls |
| --- | ---: | ---: |
| Inclusion proof only | 128/128 | 32/32 |
| Signed fresh checkpoint | 0/128 | 32/32 |

All four attack families were blocked 32/32: missing checkpoint, untrusted
signing key, expired checkpoint, and future-dated checkpoint.

## Production consequence

Strict mode now requires an Ed25519-signed, versioned checkpoint binding the
exact log ID, tree size, root SHA-256, and issuance time.  It verifies the
canonical key fingerprint and signature, exact equality with the inclusion
witness, a configured maximum age, and a configured future-skew bound.  Missing
or nonsensical configuration fails closed.

This removes the self-asserted-root hole: a repository can no longer make an
arbitrary Merkle tree authoritative merely by supplying a valid inclusion
path.  A trusted workflow can now bound the age of the root used for a
definitive scientific verdict.

## Independent audit

The zero-production-import audit independently canonicalized all 160
checkpoint statements, derived 160 key fingerprints, verified every available
signature, compared every root binding, and recomputed all freshness decisions.
It authenticated exactly 32/32 controls and 0/128 attacks.  The compressed raw
matrix is deterministic and retained with the summary and audit.

## Limitations

This authenticates one fresh root under one configured Ed25519 key.  It does
not prove append-only consistency with previous roots, global canonicity,
cross-client gossip, secure key custody, actual producer execution, or a live
deployment.  A consistency-proof gate remains required before treating the log
as append-only history.
