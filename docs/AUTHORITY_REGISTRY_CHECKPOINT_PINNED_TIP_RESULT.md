# Pinned checkpoint-history tip

## Result

The pinned-root gate accepted all **128/128** frozen tail-truncation attacks.
Each attack supplied a valid chain starting at the trusted root but withheld
the authentic newest checkpoint quorum.  The disclosed chain ended at a stale
registry under which a decisive scientific verdict remained valid.  Every
supplied signature, snapshot, root comparison, and adjacent link verified.

The corrected optional mode authenticates the other endpoint of the chain by
binding the current qualifying quorum to a trusted canonical statement digest:

- parent rooted false passes: **128/128**;
- root-and-tip false passes: **0/128**;
- reversed-order false passes: **0/128**;
- complete four-epoch controls: **32/32**;
- revocation, trust-domain, authority-quorum, and key-set rollback attacks
  blocked: **32/32 each**;
- missing, malformed, stale, wrong-namespace, wrong-epoch, and wrong-snapshot
  tip pins fail closed;
- tip mode without root mode fails closed.

## Independent audit

The zero-production-import audit independently:

- verified **1,280 Ed25519 signatures**;
- reconstructed **640 authority-registry digests**;
- replayed **480 adjacent history links**;
- checked **160 trusted-root pins**;
- checked **160 trusted-tip pins**.

Raw compressed evidence, summary, and audit artifacts reproduce byte-for-byte.

## Product consequence

Trusted workflows can enable both `require_registry_checkpoint_root=True` and
`require_registry_checkpoint_tip=True`, supplying
`trusted_registry_checkpoint_root_statement_sha256` and
`trusted_registry_checkpoint_tip_statement_sha256`.  A decisive hosted verdict
is suppressed unless the supplied history starts at the exact trusted root,
ends at the exact trusted tip, and every disclosed transition verifies.  Tip
mode refuses to run without root mode, closing the one-ended configuration
footgun.

The production workflow executes both the attack matrix and independent audit
and archives their summaries as hosted-job evidence.

## Reproduce

```bash
PYTHONPATH=src:research/scripts python \
  research/scripts/verify_authority_registry_checkpoint_pinned_tip.py
python research/scripts/audit_authority_registry_checkpoint_pinned_tip.py
```

## Claim boundary

This guarantee depends on securely provisioning the correct latest statement.
It detects rollback only relative to that trusted tip.  It cannot discover a
newer checkpoint unknown to the workflow, establish global canonicity, secure
pin distribution or storage, prevent denial of service, reveal unseen forks,
replace gossip or transparency-log proofs, or claim a deployed checkpoint
service.
