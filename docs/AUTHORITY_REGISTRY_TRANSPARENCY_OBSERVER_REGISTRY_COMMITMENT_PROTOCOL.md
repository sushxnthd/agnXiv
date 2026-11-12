# Frozen protocol: trusted observer-registry commitment

## Objective

Test whether the exact-current-view and administrative-domain quorum can be
defeated by replacing the in-process trusted observer registry. The existing
gate authenticates observer and log signatures, but the supplied observer key,
status, and domain bindings are not themselves committed to a protected value.

## Threat model

An attacker cannot forge any legitimate observer or transparency-log
signature. The workflow boundary is nevertheless allowed to substitute the
observer registry supplied to the gate. It can therefore register attacker
keys as active observers, assign those identities distinct-looking domains,
and produce a fresh exact-current-checkpoint quorum using only attacker keys.

This is a configuration-substitution attack, not a claim that a protected
deployment secret or repository setting has already been compromised.

## Frozen adversarial matrix

Generate 32 deterministic cases for each family:

1. replace both trusted observer keys and domain assignments;
2. retain observer IDs but replace their keys and domains;
3. replace status/domain metadata while using attacker-controlled registered
   identities; and
4. omit any protected observer-registry commitment while supplying a
   self-consistent attacker registry.

Every case uses a valid log-signed current checkpoint, two fresh
observer-signed exact-checkpoint statements, two apparent administrative
domains, and the configured current-view quorum. Add 32 valid controls using
the legitimate observer registry and its protected commitment.

The frozen baseline prediction is 128/128 attack false passes and 32/32 valid
controls. The commitment-bound gate must produce 0/128 attack false passes and
32/32 valid controls.

## Proposed mechanism

Canonicalize the complete trusted observer registry, including observer ID,
key fingerprint, public key, normalized administrative domain, and status.
Hash that canonical payload. Strict authorization receives the expected digest
from a protected workflow/deployment trust boundary and requires an exact
match before counting any observer or domain quorum.

Missing expected commitment, substituted keys, changed domain bindings,
revocation changes, extra entries, and removed entries must all fail closed.

## Decision rule

The mechanism passes only if:

- the existing unbound gate accepts all 128 attacker-controlled exact-current
  quorums and all 32 controls;
- the commitment-bound gate rejects all 128 attacks and accepts all controls;
- each attack family is blocked 32/32;
- a zero-production-import audit independently canonicalizes both legitimate
  and substituted registries, recomputes all digests, verifies every signature
  and checkpoint digest, and reproduces every decision;
- raw, derived, and audit artifacts are deterministic; and
- the full regression suite remains green.

Any surviving false pass or rejected valid control is preserved as a
falsification. The result will establish only cryptographic/configuration
binding to an externally supplied digest. It will not prove that real observer
organizations are independent, that keys have separate custody, that the
protected configuration is correctly administered, or that observers are
deployed and reachable. PR #50 remains draft and unmerged.
