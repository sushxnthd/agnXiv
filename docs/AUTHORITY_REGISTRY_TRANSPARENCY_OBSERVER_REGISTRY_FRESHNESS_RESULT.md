# Observer-registry rollback and namespace-binding result

## Central finding

The protected observer-registry digest remained vulnerable to configuration
rollback because it committed observer identities, keys, revocation status,
and domains without committing a deployment namespace or monotonic registry
epoch.  A once-valid digest and matching old registry could therefore remain
self-consistent after policy intended to revoke keys or change domain
assignments.  An identical observer set could also be replayed from staging
into production.

The prospectively frozen matrix produced:

| Gate | Attack false passes | Valid controls |
|---|---:|---:|
| Versionless protected digest | **128/128** | 32/32 |
| Namespace + epoch + external floor | **0/128** | 32/32 |

All four frozen families were blocked 32/32: revoked-key rollback,
administrative-domain policy rollback, cross-namespace replay, and omission of
the minimum epoch floor.

## Mechanism

Strict freshness mode now hashes a versioned canonical registry payload
containing:

- the normalized deployment namespace;
- a non-negative monotonic registry epoch; and
- the complete canonical observer-key, status, and domain list.

Authorization also requires the supplied namespace to match the expected
consumer namespace and the supplied epoch to meet an independently configured
minimum.  Missing namespace, epoch, floor, or protected digest fails closed.
Legacy callers retain the existing versionless behavior unless strict
freshness mode is explicitly enabled.

This creates an executable product consequence: a current-checkpoint quorum
cannot authorize a verdict using a stale or staging observer-policy snapshot
once the production trust boundary advances the floor and protected digest.

## Independent verification

The zero-production-import audit independently:

- reconstructed all 160 cases;
- recomputed 160 versionless and 160 versioned registry digests;
- recomputed 160 Merkle roots;
- verified 640 observer and transparency-log signatures; and
- reproduced all 160 baseline and strict decisions.

Raw, summary, and audit artifacts reproduced byte-for-byte.  Their SHA-256
digests are:

- raw: `6980e6a302c6d109f27c9cb74e3e9e8df3cf2e4efdeb21e4028835dba36db815`;
- summary: `230af74d99cf35e829a9cc3c4b2c2597313bddf2e1dad77d309e945fa0e107cb`;
- audit: `e1ff36d569cbf2de580f74260c69dccf2b5f834b856c7402f2896851b2a13832`.

The production workflow executes and preserves both the verifier and the
independent audit.

## Limits and remaining launch gates

The mechanism depends on an external trust source that advances and protects
the expected production namespace, minimum epoch, and versioned digest.  This
result does not establish that those values are deployed or independently
governed.  It also does not prove destruction of old keys, real organizational
independence, separate key custody, global observer coverage, network
availability, external security review, or a live deployment.  PR #50 remains
draft, conflicted, and unmerged.
