# Frozen protocol: same-epoch checkpoint-quorum equivocation

## Question

The snapshot-bound gate accepts a quorum only when its signed registry digest
matches the supplied authority registry. What happens when the caller supplies
two independently qualifying quorum statements for the same registry namespace
and epoch but different registry digests?

The parent implementation selects one maximum-epoch statement. It does not
reject a disclosed sibling statement at that same epoch, so selection order may
hide a cryptographically valid checkpoint equivocation.

## Frozen attack matrix

Construct 128 attacks across four same-epoch authority-policy fork families:

1. key revocation;
2. trust-domain assignment;
3. authority quorum threshold;
4. registry key-set membership.

Each attack supplies two complete checkpoint quorums. Both use trusted active
keys spanning the required independent checkpoint domains. Both sign the same
registry namespace and epoch, but one signs the supplied registry digest and
the other signs a conflicting digest. The supplied-registry quorum is ordered
first so the parent snapshot gate is predicted to issue a decisive verdict.

Construct 32 controls containing one complete, snapshot-matching quorum.

## Frozen correction

After measuring the parent, reject the entire checkpoint set if two or more
qualifying statements endorse different registry digests for the same
namespace and epoch. This check occurs before choosing the maximum epoch or
matching the supplied snapshot. It is fail-closed and independent of input
order.

## Completion gate

- parent snapshot gate false-passes all 128 disclosed equivocations;
- corrected gate false-passes 0/128;
- corrected gate accepts 32/32 non-equivocating controls;
- all four fork families are blocked 32/32;
- reversing checkpoint order cannot change the corrected verdict;
- an independent zero-agnXiv-import audit verifies every checkpoint signature,
  reconstructs every registry digest, and reproduces every verdict;
- raw and derived evidence is deterministic;
- production workflows execute and archive both verifier and audit;
- the full regression suite and lint pass.

## Claim boundary

Passing detects equivocation only when conflicting qualifying statements are
presented to the same gate. It does not discover a statement withheld from the
caller, provide checkpoint gossip or transparency, establish honest governance,
protect after threshold compromise, or claim a deployed checkpoint service.
