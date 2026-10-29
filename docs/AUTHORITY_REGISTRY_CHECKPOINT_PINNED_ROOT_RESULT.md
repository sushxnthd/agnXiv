# Pinned checkpoint-history root

## Result

The transitive history gate accepted all **128/128** frozen prefix-truncation
attacks.  Each attack omitted the authentic oldest checkpoint quorum and
supplied a later, internally valid signed suffix.  Because the parent gate
treated the oldest disclosed statement as its root, every disclosed signature
and link verified and a decisive scientific verdict survived.

The corrected optional mode binds the oldest qualifying supplied quorum to a
trusted canonical statement digest provisioned by the workflow:

- parent unpinned false passes: **128/128**;
- pinned-root false passes: **0/128**;
- reversed-order false passes: **0/128**;
- complete three-epoch controls: **32/32**;
- revocation, trust-domain, authority-quorum, and key-set truncations blocked:
  **32/32 each**;
- missing, malformed, wrong-namespace, wrong-epoch, and wrong-snapshot pins all
  fail closed.

The independent audit imports zero agnXiv modules.  It verified **704 Ed25519
signatures**, reconstructed **480 registry digests**, replayed **160 current
history links**, and independently checked **160 trusted-root comparisons**.
Raw compressed evidence, summary, and audit files reproduce byte-for-byte.

## Product consequence

Trusted workflows can enable `require_registry_checkpoint_root=True` and pass
`trusted_registry_checkpoint_root_statement_sha256`.  A decisive hosted verdict
is then suppressed unless the oldest disclosed qualifying checkpoint commits
to exactly that namespace, epoch, and registry snapshot.  The production gate
executes and archives the attack matrix and zero-import audit.

## Reproduce

```bash
PYTHONPATH=src:research/scripts python \
  research/scripts/verify_authority_registry_checkpoint_pinned_root.py
python research/scripts/audit_authority_registry_checkpoint_pinned_root.py
```

## Claim boundary

This guarantee is only as trustworthy as the provisioned root pin.  It does
not establish global canonicity, secure pin distribution or storage, reveal
never-observed forks, provide gossip or transparency-log inclusion, prevent
history deletion, guarantee governance or key custody, or claim a deployed
checkpoint service.
