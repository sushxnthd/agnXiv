# Frozen protocol: recursive checkpoint-history commitment

## Question

The trusted root and tip statement digests bind namespace, epoch, and registry
snapshot, but the tip digest omits `previous_statement_sha256`. Can two fully
authenticated histories with the same pinned endpoints carry different
intermediate registry paths and both pass the current transitive-chain gate?

## Frozen attack matrix

Construct 128 three-epoch path-substitution attacks across four intermediate
authority-policy families: key revocation, trust-domain assignment, authority
quorum, and key-set membership. Each pair has:

- the same signed root statement;
- the same root statement pin;
- the same final registry snapshot and final statement tuple;
- the same trusted tip statement pin;
- a different signed intermediate registry snapshot and predecessor link.

All statements use two Ed25519 checkpoint signers in distinct trust domains.
The parent prediction is that root + tip + transitive-chain mode accepts both
paths because the pinned tip digest does not commit to its predecessor link.

Construct 32 honest three-epoch controls.

## Repair target

Add an opt-in recursive history-commitment mode. Define a signer-independent
linked-statement digest over namespace, epoch, registry digest, and the exact
predecessor digest. Require each successor to name the linked digest of its
adjacent predecessor. Require a workflow-provisioned trusted commitment to
match the linked digest of the current quorum. The final commitment must
therefore transitively bind every retained statement back to the root.

The mode must fail closed when the commitment is missing, malformed, stale,
for another namespace or path, when current signers disagree on the link, or
when enabled without root, tip, and transitive-chain validation.

## Success criteria

- Parent endpoint-pinning false passes: 128/128.
- Recursive-commitment false passes: 0/128.
- Honest controls: 32/32.
- All four attack families blocked: 32/32 each.
- Independent zero-import audit reconstructs every registry digest, verifies
  every Ed25519 signature, replays every recursive link, and checks every
  trusted final commitment.
- Deterministic artifacts reproduce byte-for-byte; full regression and Ruff
  pass.

## Stop conditions

Stop and preserve a negative result if the parent gate already rejects the
endpoint-preserving substitutions, if any honest control abstains, or if the
new commitment does not distinguish the two paths without signer identity.

## Scope

Passing binds the disclosed signed path to a correctly provisioned final
commitment. It cannot reveal an unseen later checkpoint, establish global
canonicity, protect the trusted commitment store, or replace gossip and a
public append-only transparency log.
