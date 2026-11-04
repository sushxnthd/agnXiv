# Frozen protocol: pinned checkpoint-history tip

## Threat

The pinned-root gate authenticates the oldest disclosed checkpoint and every
adjacent link, but it does not prove that the disclosed chain reaches the
newest checkpoint known to the trusted workflow.  A server can withhold an
authentic newest quorum and replay a complete, internally valid chain ending
at an older registry epoch.  Every disclosed signature, root comparison, and
history link remains valid.

## Frozen attack matrix

Before implementation, construct four registry-change families:

1. authority revocation omitted;
2. trust-domain restriction omitted;
3. authority-quorum increase omitted;
4. checkpoint-key-set truncation omitted.

For each family, generate 32 deterministic cases.  Each case contains a
four-epoch authentic chain rooted at a workflow-pinned statement.  The parent
gate receives only the first three epochs and evaluates a paper attested under
the stale third registry.  The withheld fourth epoch contains the security
change.

Expected parent result: **128/128 false decisive verdicts** despite valid root
pinning and transitive-chain validation.

## Correction under test

Add an optional trusted-tip mode that requires the current qualifying quorum
to hash to a workflow-provisioned canonical statement digest committing to
registry namespace, epoch, and registry snapshot.  Tip mode must fail closed
unless root mode is also enabled, so callers cannot authenticate only one end
of the chain by accident.

## Acceptance criteria

- parent rooted false passes: `128/128`;
- root-and-tip false passes: `0/128`;
- reversed-order false passes: `0/128`;
- complete four-epoch controls: `32/32`;
- each attack family blocked: `32/32`;
- missing, malformed, stale, wrong-namespace, wrong-epoch, and wrong-snapshot
  tip pins fail closed;
- tip-without-root configuration fails closed;
- independent audit imports zero agnXiv modules and reconstructs signatures,
  registry digests, history links, root comparisons, and tip comparisons;
- deterministic evidence regenerates byte-for-byte;
- full regression, Ruff, and diff-integrity checks pass.

## Product boundary

Success proves rollback resistance only relative to a correctly provisioned
trusted tip statement.  It does not discover a newer statement unknown to the
workflow, provide secure pin distribution or storage, establish global
canonicity, prevent denial of service, replace gossip or transparency logs, or
claim a deployed checkpoint service.
