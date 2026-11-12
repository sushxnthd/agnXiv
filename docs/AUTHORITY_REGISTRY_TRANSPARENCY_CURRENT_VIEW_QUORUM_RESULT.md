# Current-view quorum closes the partition coverage gap

## Result

The existing authenticated, cross-domain gossip rule had a launch-critical
coverage gap: observers could agree on a fresh observation of an older
checkpoint while the client evaluated a newer checkpoint that no independent
observer had witnessed.

The frozen matrix confirmed the failure and the repair:

| Gate | Attack false passes | Valid controls |
|---|---:|---:|
| Pairwise cross-domain gossip | 128/128 | 32/32 |
| Current-view observer/domain quorum | 0/128 | 32/32 |

All observations, checkpoints, and consistency proofs in the attack matrix
were valid.  The failure was not caused by bad signatures, stale timestamps,
invalid Merkle proofs, duplicate identities, or same-domain observers.  It was
caused by failing to bind the quorum to the client's exact current root.

## Product consequence

Strict transparency gossip now requires the already configured minimum number
of observers and administrative domains to attest the exact signed checkpoint
being evaluated.  Older mutually consistent views remain useful evidence but
cannot authorize the current verdict.  During a partition, missing current-root
coverage therefore produces an explicit abstention.

The lower-level verifier retains zero defaults for the new current-checkpoint
thresholds so existing analytical callers remain explicit.  The production
authority gate sets both current-view thresholds to its strict gossip observer
and domain thresholds and supplies the current signed checkpoint.

## Attack families

The current-view gate blocked all 32 deterministic cases in each family:

- two cross-domain observers attesting only the old root;
- two old-root observers plus one current-root observer;
- three old-root observers across multiple domains; and
- one old-root and one current-root observer connected by a valid append-only
  consistency proof.

The last family establishes the distinction precisely: append-only ancestry
does not prove that a quorum has observed the current root.

## Independent audit

The zero-production-import audit independently verified 160 cases, 768 Ed25519
signatures, 320 Merkle roots, every checkpoint digest, all supplied consistency
proofs, and the current-root observer/domain counts.  It reproduced 160/160
baseline accepts, 0/128 hardened attack passes, and 32/32 controls.

The three evidence SHA-256 digests are:

- raw matrix: `2a9f680a87af53edeed901c9e12b7f4c88bf6268413187943afd3b926778d7db`;
- summary: `2108fafd5f3427b80ac73480fa35d76584f8efb1f970c2097c8f75bcb28a9a08`;
- audit: `9d1c94543193e9d6b75e829f839b7564552b0e54519afe2bff7fab2d5e86ce44`.

A clean rerun reproduced every artifact byte-for-byte.  Ruff, the three focused
gossip regressions, and the full 336-test suite pass locally.

## Limits

This gate proves only that configured trusted identities and administrative
domain labels signed the exact current checkpoint.  It does not prove real
organizational independence, separate key custody, geographical distribution,
deployment, continuous network reachability, or external audit.  A partition
can reduce availability by forcing abstention; it cannot be converted into a
pass.  PR #50 remains draft, conflicted, and unmerged, and no live deployment
is claimed.
