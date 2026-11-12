# Trusted observer-registry commitment result

## Central finding

The exact-current-view and administrative-domain quorum remained vulnerable to
configuration substitution. The gate authenticated every observer and log
signature, but treated the supplied observer-key and domain registry as
trusted input. An attacker who replaced that registry could register its own
keys under two apparent domains and obtain a definitive verdict.

In the prospectively frozen matrix:

| Gate | Attack false passes | Valid controls |
|---|---:|---:|
| Unbound exact-current-view quorum | **128/128** | 32/32 |
| Protected observer-registry commitment | **0/128** | 32/32 |

All four attack families were blocked 32/32: new Sybil identities, trusted-ID
key rebinding, revocation/metadata rollback, and omission of the protected
commitment.

## Mechanism

The gate now canonically commits the complete trusted observer registry:

- observer identity;
- key fingerprint and public key;
- normalized administrative-domain assignment; and
- active or revoked status.

Strict authorization compares this canonical SHA-256 digest with an expected
value supplied by the protected workflow or deployment boundary before any
observer or domain counts toward quorum. Missing commitments and any registry
substitution fail closed.

This makes domain diversity an executable property of one externally pinned
registry snapshot rather than a claim made by the same untrusted input being
evaluated.

## Independent verification

The zero-production-import audit independently:

- reconstructed all 160 cases;
- recomputed 160 Merkle roots and 160 observer-registry digests;
- verified 640 observer/log signatures;
- reproduced all baseline and commitment-bound decisions; and
- confirmed 0/128 attack false passes and 32/32 accepted controls.

Raw, summary, and audit artifacts reproduce deterministically. The raw result
SHA-256 is
`89b86cad7f2dec49cec2d74f7db279afe6a03c7ec61dd3eb4abc69c1ce86bc4b`;
the summary SHA-256 is
`e74da3f0243bc99b3945a5e16e8c0a4b49cb84b999d316a704cc7bdfcb2e613d`;
and the audit SHA-256 is
`1ae6e217dfe75d57b0b84be18b9ff39d819d51ec60825ccce7d91108bb64d135`.

## Production consequence and limits

The hosted production gate now executes the current-view and observer-registry
commitment matrices and preserves their audit outputs. Production readiness
still requires the expected digest to be provisioned through independently
governed protected configuration.

This result does not prove that named organizations are independent, that
observer keys have separate custody, that the protected configuration is
correctly administered, or that any observer network is deployed and
reachable. No live deployment is claimed. PR #50 remains draft, conflicted,
and unmerged.
