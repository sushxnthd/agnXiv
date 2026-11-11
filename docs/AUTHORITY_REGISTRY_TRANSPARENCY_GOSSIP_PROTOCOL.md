# Frozen protocol: authenticated cross-client transparency gossip

## Motivation

The append-only consistency gate proves that one current checkpoint extends
one authenticated prior checkpoint.  It does not establish that two clients
were shown the same log history.  A malicious log can maintain two internally
append-only views and give each client a valid signature, inclusion proof, and
local consistency proof.

This protocol is frozen before opening the attack matrix.  It tests whether
authenticated observer gossip closes that remaining split-view false-pass.

## Mechanism under test

Each observer signs a statement binding its identity, observation time, and
the digest of one log-signed checkpoint.  A strict verdict requires:

1. at least two distinct active observer identities;
2. valid observer and log signatures;
3. timezone-aware, freshness-bounded observations;
4. one common log identifier;
5. identical roots for equal tree sizes; and
6. a valid endpoint-bound consistency proof for every unequal-size pair.

The gate abstains on missing or unverifiable cross-view evidence.  It reports
equal-size root disagreement as direct split-view evidence.

## Frozen matrix

Use 32 deterministic cases per family and compare the existing per-client
consistency gate with the authenticated gossip gate.

Attack families:

- `same_size_fork`: two valid log-signed checkpoints at the same size have
  different roots;
- `parallel_append_only_forks`: two clients each have a valid local extension
  from a common old checkpoint, but their equal-size current roots differ;
- `missing_cross_view_proof`: observers report unequal sizes without a proof
  relating their views;
- `tampered_cross_view_proof`: the supplied pairwise proof is modified.

Controls use two authenticated observers and either the same checkpoint or a
valid unequal-size append-only extension.

## Frozen predictions

- The per-client append-only gate will produce a definitive false pass on all
  128 attacks when each view is evaluated in isolation.
- The authenticated gossip gate will produce 0/128 attack false passes.
- The authenticated gossip gate will accept 32/32 controls.
- Direct forks will be distinguished from evidence insufficiency: equal-size
  root disagreements are split-view detections, while absent cross-view proofs
  are conservative abstentions.

## Independent verification

A zero-production-import audit must independently verify observer signatures,
log signatures, checkpoint digests, Merkle roots, and cross-view consistency
proofs.  Raw cases, a derived summary, and negative controls must be retained
deterministically.  Targeted lint and the full regression suite must pass.

## Decision rule

The launch mechanism is supported only if every frozen count and reason class
matches, all valid controls pass, and the independent audit agrees.  Any
mismatch is preserved as a falsification.  No live deployment, secure key
custody, or global monitor coverage is claimed.
