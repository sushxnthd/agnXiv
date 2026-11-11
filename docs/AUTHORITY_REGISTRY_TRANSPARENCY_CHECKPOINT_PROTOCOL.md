# Frozen protocol: authenticated fresh transparency checkpoints

## Failure being tested

The current gate verifies RFC 6962-style inclusion against the root embedded in
the committed witness.  It does not authenticate that root or establish when
the checkpoint was issued.  An attacker can therefore construct a valid tree
around the provenance statement and self-assert its root, or replay an old
otherwise legitimate root.

## Frozen adversarial matrix

Generate 128 cases, 32 in each family.  Every case carries a valid provenance
signature, a committed inclusion witness, and a valid Merkle inclusion proof,
so the parent inclusion gate is predicted to produce 128/128 definitive false
passes.

1. missing signed transparency checkpoint;
2. checkpoint signed by an untrusted Ed25519 key;
3. correctly signed checkpoint older than the configured maximum age;
4. correctly signed checkpoint issued beyond the configured future-skew bound.

Generate 32 matched controls with the same log ID, tree size, root, and proof,
but a trusted signature and an issuance time inside the freshness window.

## Required correction

Add a canonical versioned transparency-checkpoint statement containing log ID,
tree size, root SHA-256, and timezone-aware issuance time.  Its signed envelope
must carry the canonical Ed25519 public-key fingerprint.  Strict mode must:

- require the preceding inclusion and digest-attestation authentication modes;
- require exact equality between checkpoint and inclusion-witness log ID, tree
  size, and root;
- require a configured trusted Ed25519 public key and matching fingerprint;
- verify the signature over the canonical checkpoint statement;
- reject checkpoints older than the configured maximum age;
- reject checkpoints farther in the future than the configured skew allowance;
- fail closed on missing, malformed, mismatched, or nonsensical configuration.

The corrected gate must accept 0/128 attacks and 32/32 controls.  A separate
zero-production-import audit must independently canonicalize every checkpoint,
fingerprint the key, verify every signature, compare every witness binding, and
recompute every freshness decision.

## Claim boundary

Passing authenticates one fresh log root under one configured key.  It does not
prove append-only consistency with earlier roots, global log canonicity,
cross-client gossip, key security, actual producer execution, or a live
deployment.  Those remain explicit launch gates.
