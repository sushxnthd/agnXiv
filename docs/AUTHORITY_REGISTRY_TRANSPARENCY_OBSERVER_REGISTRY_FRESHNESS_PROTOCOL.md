# Frozen protocol: observer-registry rollback and namespace binding

## Objective

Test whether the protected observer-registry digest can authorize a stale or
cross-environment registry snapshot.  The current commitment binds observer
IDs, keys, status, and administrative domains, but does not bind a registry
namespace or monotonic epoch.  If protected configuration retains a once-valid
digest, the matching old registry remains self-consistent and can still
satisfy the exact-current-checkpoint quorum.

This is a configuration-rollback threat model.  It does not assume a digest
collision, forged signature, or compromise of current observer keys.  It does
assume that old observer keys can still produce signatures after the registry
policy intended to revoke or regroup them.

## Frozen adversarial matrix

Generate 32 deterministic cases for each family:

1. `revoked_key_rollback`: replay the preceding active registry after its two
   observer keys have been revoked in the current epoch;
2. `domain_policy_rollback`: replay the preceding two-domain assignment after
   the current policy places those observers in one administrative domain;
3. `namespace_replay`: replay an otherwise byte-identical staging registry in
   the production consumer; and
4. `missing_minimum_epoch`: provide the current versioned registry and digest
   but omit the externally configured monotonic epoch floor.

Every case uses a valid log-signed current checkpoint and two fresh,
observer-signed statements for that exact checkpoint.  Add 32 valid controls
using namespace `production`, epoch 41, the current observer registry, its
versioned protected digest, and minimum epoch 41.

The frozen prediction is:

| Gate | Attack false passes | Valid controls |
|---|---:|---:|
| Versionless digest commitment | 128/128 | 32/32 |
| Namespace + epoch + floor binding | 0/128 | 32/32 |

## Proposed mechanism

Introduce a versioned canonical commitment whose payload contains:

- schema version;
- normalized registry namespace;
- non-negative monotonic registry epoch; and
- the complete canonical observer list already bound by the prior mechanism.

Strict mode requires the supplied namespace to match the expected consumer
namespace, the supplied epoch to meet an independently configured minimum,
and the versioned payload digest to match protected configuration.  Missing
namespace, epoch, floor, or protected digest fails closed.  Legacy callers
retain the existing versionless commitment unless strict freshness mode is
explicitly enabled.

## Decision rule

The mechanism passes only if:

- the versionless commitment accepts all 128 attack cases and all 32 controls;
- strict freshness rejects all 128 attacks and accepts all 32 controls;
- each frozen family is blocked 32/32;
- a zero-production-import audit independently reconstructs canonical
  versioned payloads, verifies all observer and log signatures, recomputes all
  registry and checkpoint digests, and reproduces every decision;
- raw, derived, and audit artifacts reproduce byte-for-byte;
- the production workflow executes both verifier and audit; and
- Ruff and the complete regression suite pass.

Any surviving strict false pass or rejected valid control is preserved as a
falsification.

## Claim boundary

Passing establishes an executable rollback boundary only when an external
trust source advances the minimum epoch and protects the expected namespace
and digest.  It does not establish that this configuration is deployed, that
old keys are destroyed, that administrative domains are genuinely
independent, that observer infrastructure is reachable, or that a live
production service exists.  PR #50 remains draft and unmerged.
