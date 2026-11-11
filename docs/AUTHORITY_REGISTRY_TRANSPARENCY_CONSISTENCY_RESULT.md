# Authenticated transparency checkpoints now require append-only consistency

## Result

A fresh signed checkpoint is not enough to establish log history. In the
frozen matrix, the existing authenticated-checkpoint gate accepted every
attack because each replacement tree had a valid current signature, bounded
freshness, and a valid inclusion path in isolation.

| Gate | Attack false passes | Valid controls |
| --- | ---: | ---: |
| Signed fresh checkpoint only | 128/128 | 32/32 |
| Prior checkpoint + consistency proof | 0/128 | 32/32 |

All four attack families were blocked 32/32: missing prior checkpoint,
non-advancing tree, rewritten historical prefix, and tampered consistency
path. Separate fail-closed controls rejected a missing proof, endpoint
mismatch, invalid prior signature, and inconsistent checkpoint timestamps.

## Production consequence

Strict mode now requires an authenticated previous checkpoint and an RFC
6962-style consistency witness bound to the exact previous and current signed
roots. It verifies:

- the previous checkpoint under the configured Ed25519 log key;
- identical log IDs and exact witness endpoint binding;
- strict tree-size advancement;
- strictly increasing timezone-aware issuance times; and
- cryptographic append-only consistency between the two roots.

This closes the signed-replacement-history hole. A log operator cannot obtain
a definitive scientific verdict merely by signing a fresh tree that rewrites
previously authenticated leaves.

## Independent audit

The zero-production-import audit independently recomputed 320 Merkle roots,
checked 288 checkpoint signatures, and evaluated all 160 matrix cases. It
authenticated exactly 32/32 controls and 0/128 attacks. The compressed raw
matrix, derived summary, and audit are retained deterministically.

## Limits

This proves append-only extension between two authenticated checkpoints under
one configured key. It does not prove global canonicity, cross-client gossip,
absence of split views, secure key custody, actual producer execution, or a
live deployment. Multi-observer gossip and split-view detection remain launch
requirements.
