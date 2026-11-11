# Authenticated gossip closes the local-consistency split-view gap

## Prospective result

Every frozen prediction passed.

| Gate | Attack false passes | Valid controls |
| --- | ---: | ---: |
| Per-client append-only consistency | 128/128 | 32/32 |
| Authenticated cross-client gossip | 0/128 | 32/32 |

All four attack families were blocked 32/32: same-size forks, parallel
append-only forks, missing cross-view proofs, and tampered cross-view proofs.
The gate classified all 64 equal-size root disagreements as direct split-view
evidence.  Missing or invalid unequal-size proofs caused conservative
abstention rather than a false allegation of equivocation.

## Mechanism

Each client observation now binds an observer identity, observation time, and
the digest of one log-signed checkpoint under a separate Ed25519 observer key.
A definitive verdict requires at least two distinct active observers, valid
observer and log signatures, freshness-bounded timestamps, one log identity,
identical roots at equal sizes, and a valid endpoint-bound RFC 6962 consistency
proof for every unequal-size pair.

This changes a concrete production decision.  Two individually valid local
histories can no longer independently authorize a definitive scientific
verdict when they disagree or cannot be related cryptographically.

## Independent audit

The zero-production-import audit independently checked 640 signatures, 480
Merkle roots, all 160 cases, and every supplied cross-view proof.  It recovered
0/128 accepted attacks, 32/32 accepted controls, and all 64 direct split-view
detections.

## Limits

This is a deterministic adversarial matrix, not evidence of a deployed gossip
network.  Observer identifiers are only independent when their private keys
and administrative domains are genuinely separate.  The result does not
establish global monitor coverage, secure key custody, availability under
network partition, live-log correctness, or scientific validity of logged
claims.  PR #50 remains draft and no deployment is claimed.

## Reproducibility

- Frozen protocol commit: `3838a08c18e29cd1e2d2a50f777c9b31d6c5b5c7`.
- Compressed raw matrix SHA-256: `966fc6dffd963e676f77f8ecf93698ed15221c68e8abf1ee6f717ccbd135e83c`.
- Derived summary SHA-256: `5122ce4836b1ad64d4e04a6b34997d27e71625c18a41f064c99fcbf1d9aeaf87`.
- Independent audit SHA-256: `e1420397721af89670e42fbb0b83f47e4c471ae5a0a9bc047f71103ea1deddf6`.
- Ruff: passed.
- Full local regression: 334 passed.
