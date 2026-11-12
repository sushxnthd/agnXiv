# Administrative-domain quorum closes observer-identity Sybil false passes

## Prospective result

Every frozen prediction passed.

| Gate | Attack false passes | Valid controls |
| --- | ---: | ---: |
| Distinct authenticated observer IDs | 128/128 | 32/32 |
| Trusted administrative-domain quorum | 0/128 | 32/32 |

Each attack family was blocked 32/32: two same-domain identities, three
same-domain identities, canonical aliases of one domain, and legacy observers
without a domain binding.

## Mechanism

The trusted observer registry now carries an optional canonical
`administrative_domain` binding.  Values are stripped and case-folded before
use.  Strict verdict authorization independently configures both a minimum
authenticated-observer count and a minimum authenticated-domain count.

The low-level gossip checker preserves its previous identity-only behavior
when the domain threshold is disabled, while the hosted verdict boundary now
defaults to two distinct trusted administrative domains.  This makes the
production consequence explicit: multiple identities controlled by one
registered domain cannot authorize a definitive scientific verdict.

## Independent audit

The zero-production-import audit independently reconstructed all 160 cases,
verified 704 Ed25519 observer/log signatures, recomputed 160 Merkle roots,
canonicalized every trusted domain, and reproduced exactly 128 identity-only
attack acceptances, zero domain-quorum attack acceptances, and 32 valid
controls.

The prior gossip matrix remains backward-compatible when its new domain
threshold is disabled.  Targeted Ruff passed and the complete local regression
passed 335 tests.

## Trust boundary and launch status

This mechanism enforces the independence policy recorded in a trusted
registry; it cannot prove that the registry is honest or that two named domains
are organizationally independent.  It also does not establish separate key
custody, live observer deployment, global coverage, partition availability, or
scientific correctness of logged claims.  Those remain external governance,
security-audit, and production-launch gates.  No live deployment is claimed.

PR #50 remains draft, conflicted, and unmerged.

## Reproducibility

- Frozen protocol commit: `d2415f0f74df45e8439c5589b5163e73c9125feb`.
- Pre-outcome trust-boundary correction: `56663bec8eb0b27372693d27d5e1b24ee93c92da`.
- Compressed raw matrix SHA-256: `1013239438bb106d0ffb7d338e54e9482586c4e2ef73eaa1ce3fc055474310f9`.
- Derived summary SHA-256: `aec136284f030ea5051e719f61b274264a0faf5580fc7d95937a3e47b210a6d6`.
- Independent audit SHA-256: `d84d5f3fcca9fc27c2a7424f9e12d35cec3ff4438621eb9041b5ed81396ffaf9`.
- Full local regression: 335 passed.
