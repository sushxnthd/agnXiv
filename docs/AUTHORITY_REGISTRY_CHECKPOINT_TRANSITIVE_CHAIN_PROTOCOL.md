# Frozen protocol: transitive checkpoint-history validation

Status: frozen before implementation and prospective attack execution.

## Threat

The current chain gate authenticates every supplied historical checkpoint but
validates only the link from the current quorum to the latest retained quorum.
It does not require earlier retained quorums to form one continuous chain.
Consequently, an internally detached or reordered historical prefix can remain
beneath an otherwise valid latest-to-current transition without affecting the
verdict.

## Predicted correction

Add an optional transitive-chain mode.  After authenticating quorums, the gate
must group qualifying historical statements by namespace and epoch, require a
unique statement at every retained epoch, sort them by epoch, and validate each
adjacent successor link.  The current quorum's link must still match the latest
retained statement.

The mode must fail closed when:

- a retained successor has a missing, malformed, mixed, or stale link;
- a successor links to a non-adjacent retained statement;
- retained epochs do not strictly increase;
- a retained epoch has an ambiguous qualifying statement; or
- the current transition is invalid under the existing chain rules.

The oldest supplied retained statement is an explicit trust anchor for this
bounded check; no predecessor is required for it.

## Frozen attack matrix

- 128 detached-prefix attacks across revocation, trust-domain, authority-quorum,
  and key-set registry forks.  The parent latest-link gate is predicted to
  return a definitive verdict; transitive mode must abstain.
- 32 correctly linked three-epoch controls must remain definitive.
- Reversed checkpoint order must not alter any verdict.
- Missing, malformed, mixed, skipped, and backward historical links must fail
  closed.
- Independent verification must reconstruct every registry and statement
  digest, verify every Ed25519 signature, validate every adjacent link, and
  import zero agnXiv modules.
- Raw, summary, and audit artifacts must reproduce byte-for-byte.

## Claim boundary

This proves internal continuity only for the authenticated history supplied to
the gate, rooted at its oldest supplied statement.  It cannot prove that the
root is globally canonical, detect omitted history before that root or views
never observed by a trusted party, prevent deletion, provide cross-client
gossip or transparency-log inclusion, establish honest governance or key
custody, guarantee availability, or claim a deployed checkpoint service.

Kill or reformulate if the parent gate does not false-pass the frozen attack,
if any transitive-chain attack remains definitive, if any valid control
abstains, or if the independent audit disagrees.
