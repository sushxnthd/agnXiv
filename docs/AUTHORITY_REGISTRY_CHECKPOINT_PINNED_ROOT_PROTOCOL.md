# Frozen protocol: pinned checkpoint-history root

## Threat model

The transitive checkpoint-history gate validates every adjacent quorum in the
history supplied to one invocation.  It treats the oldest supplied statement
as its trust root.  An adversary may therefore omit an earlier authentic
prefix and present a valid signed suffix whose internal links all verify.

This is a prefix-truncation attack, not a signature forgery: every disclosed
checkpoint is authentic and every disclosed transition is valid.

## Frozen attack matrix

Generate 128 attacks across the existing revocation, trust-domain,
authority-quorum, and key-set registry families, 32 deterministic cases per
family.  Each case has an authentic three-epoch chain but supplies only the
last historical quorum and the current quorum.  The workflow retains the
statement digest of the omitted root as an independently trusted pin.

The unpinned transitive gate is expected to issue a decisive verdict in all
128 cases.  This parent failure is preserved as evidence.

## Correction

Add an optional fail-closed mode requiring the oldest qualifying supplied
historical quorum to hash to a caller-provided, canonical statement digest.
The digest commits to registry namespace, epoch, and registry snapshot digest.
The pin must be lowercase hexadecimal SHA-256 and is configuration supplied by
the trusted workflow, never by the paper under test.

## Decisive criteria

- parent unpinned false passes: **128/128**;
- pinned-root false passes: **0/128**;
- reversed-order false passes: **0/128**;
- complete three-epoch controls: **32/32**;
- each attack family blocked: **32/32**;
- missing, malformed, wrong-namespace, wrong-epoch, and wrong-snapshot pins
  fail closed;
- independent audit imports zero `agnxiv` modules and rechecks every signature,
  registry digest, statement digest, link, pin, and verdict count;
- raw, summary, and audit artifacts reproduce byte-for-byte.

## Claim boundary

The experiment proves continuity only to a correctly provisioned trusted root
statement.  It does not prove that the pin is globally canonical, secure its
distribution or storage, discover unseen forks after the root, provide gossip
or transparency-log inclusion, prevent deletion, or claim a deployed service.
