# Frozen protocol: current-view transparency quorum

## Launch-critical question

The authenticated gossip gate compares observer views with one another, but it
does not currently require those observers to attest the exact transparency
checkpoint being evaluated by the client.  During a partition, two independent
observers may freshly re-observe an older agreed checkpoint while the log gives
the client a newer private fork.  Pairwise observer agreement then passes even
though no independent domain has witnessed the client's current root.

## Frozen attack matrix

Generate 32 deterministic seeds for each attack family:

1. two cross-domain observers freshly attest only the old checkpoint;
2. two observers attest the old checkpoint and one observer attests the
   client's current checkpoint;
3. three observers across two domains attest only the old checkpoint; and
4. one current observer plus one old observer have a valid append-only proof
   between their views.

All checkpoints and observations are validly signed, fresh, and use the same
log identifier.  The client's current checkpoint is a valid append-only
extension of the old checkpoint.  These are partition-coverage attacks, not
signature, freshness, or Merkle-proof failures.

Add 32 controls in which two trusted observers from distinct administrative
domains both attest the exact client checkpoint.

## Frozen prediction

The existing pairwise gossip rule will falsely pass all 128 attacks and all 32
controls.  A current-view quorum requiring two authenticated observers from
two administrative domains to attest the exact client checkpoint will pass
zero attacks and all 32 controls.

The strict production gate must bind its already configured minimum observer
and administrative-domain thresholds to the current signed checkpoint.  A
partition or missing observer therefore produces abstention, never a pass.

## Completion criteria

The experiment passes only if:

- baseline false passes are exactly 128/128;
- current-view quorum false passes are 0/128;
- controls pass 32/32;
- deterministic evidence records all signed checkpoints, observations, trust
  bindings, and blockers;
- a zero-production-import audit independently verifies signatures, Merkle
  roots, exact checkpoint digests, observer counts, and domain counts;
- focused and full regressions pass; and
- documentation states that cryptographic quorum enforcement does not prove
  real organizational independence, deployment, or network reachability.

Any attack pass, control failure, or audit disagreement is retained as a
falsification.  PR #50 remains draft and unmerged.
