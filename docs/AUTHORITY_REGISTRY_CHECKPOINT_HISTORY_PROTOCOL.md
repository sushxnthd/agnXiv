# Frozen protocol: persisted checkpoint-history consistency

## Question

The current gate rejects conflicting same-epoch checkpoint quorums only when
both are supplied in one invocation. Can a server show one valid snapshot to a
client, later show only a conflicting same-namespace, same-epoch quorum, and
obtain a decisive verdict because the earlier observation is withheld?

## Frozen attack matrix

Construct 128 sequential split-view attacks across the existing four registry
policy families: key revocation, trust-domain assignment, authority quorum, and
key-set membership. Each case contains:

1. a previously observed, independently qualifying two-domain checkpoint quorum
   for the legitimate registry digest;
2. a currently presented, independently qualifying quorum at the same namespace
   and epoch for the conflicting digest;
3. authority attestations valid under the currently supplied conflicting
   registry.

The parent gate receives only the current quorum and is predicted to issue a
decisive verdict in 128/128 cases. The corrected gate receives the same current
quorum plus the persisted signed observation history and must abstain in 128/128.

Construct 32 matching-history controls and 32 prior-epoch controls. Both must
retain decisive verdicts. Reversing signature and history order must not change
the result.

## Required implementation properties

- Historical entries are authenticated under the same explicit checkpoint-key
  trust root and quorum policy as current entries.
- Historical entries can reveal equivocation but cannot satisfy the required
  current checkpoint quorum by themselves.
- Conflicting qualifying digests at the same namespace and epoch force
  abstention independent of order.
- Matching same-epoch history and nonconflicting prior epochs remain accepted.
- When history consistency is required, silently omitting the persisted history
  forces abstention.
- Independent audit verifies signatures, digest sets, and all verdicts without
  importing agnXiv.

## Kill criteria

Kill or reformulate on any attack false pass, control abstention, order
dependence, historical-only quorum acceptance, invalid-signature acceptance, or
independent-audit mismatch. Preserve the first counterexample.

## Claim boundary

This experiment can prove consistency against signed observations actually
retained and supplied by the trusted workflow. It cannot discover views never
observed, prove that storage is append-only, prevent deletion of history, provide
cross-client gossip, establish transparency-log inclusion, or claim a deployed
checkpoint distributor.
