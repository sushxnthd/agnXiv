# Frozen protocol: checkpoint-bound registry snapshot

**Frozen before attack evaluation.**

## Question

The existing authenticated quorum signs a registry namespace and minimum epoch, but not the authority-registry contents. Can a valid checkpoint quorum for a legitimate snapshot be replayed against a different registry snapshot carrying the same namespace and epoch?

## Frozen attack matrix

Construct 128 same-epoch fork attacks across four authority-policy families: key revocation, trust-domain assignment, signature quorum, and key-set membership. Each attack supplies a legitimate and forked registry with the same namespace and epoch, authority attestations valid under the fork, and two valid checkpoint signatures from distinct trust domains over the legitimate namespace and epoch.

The parent quorum gate is predicted to accept both snapshots because its signed statement does not identify registry contents. Construct 32 controls whose registry snapshot is the one endorsed by the checkpoint quorum.

## Corrected mechanism

Extend the canonical signed checkpoint scope with the SHA-256 digest of the authority-registry snapshot. Add an explicit snapshot-binding requirement. In that mode:

- all signatures in a qualifying quorum must endorse the same namespace, epoch, and registry digest;
- the supplied registry namespace and epoch must satisfy the existing checks;
- the supplied registry digest must equal the signed digest;
- missing or malformed digest binding fails closed;
- legacy floor-only mode remains explicit and is not silently described as snapshot-consistent.

## Acceptance criteria

- Parent quorum false-passes all 128 fork attacks.
- Snapshot-bound quorum false-passes 0/128 attacks.
- Snapshot-bound quorum accepts 32/32 controls.
- Duplicate identities, one-domain quorums, disagreeing statements, revoked keys, and singular checkpoints remain blocked.
- An independent standard-library audit verifies every signature and digest decision with zero agnXiv imports.
- Full tests, deterministic evidence, Ruff, and diff checks pass.

## Kill criteria and limitations

Any fork accepted in snapshot-bound mode kills the mechanism. Any control rejected prevents production use.

Passing does not establish honest checkpoint governance, secure key installation, threshold-compromise safety, availability, append-only consistency between epochs, or a live checkpoint distributor. It proves only that a valid quorum statement cannot be detached from the exact registry snapshot it endorsed.
