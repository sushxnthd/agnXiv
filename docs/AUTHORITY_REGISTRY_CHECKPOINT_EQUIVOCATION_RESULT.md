# Same-epoch checkpoint-quorum equivocation

## Result

The snapshot-bound checkpoint gate previously selected one maximum-epoch
quorum statement even when the caller disclosed another independently
qualifying statement for the same registry namespace and epoch but a different
registry digest. With the supplied-registry statement ordered first, the parent
gate issued a decisive verdict on all 128 attacks.

The gate now detects conflicting digests among qualifying statements before it
selects an epoch or compares the supplied registry. Any such equivocation makes
the hosted scientific verdict abstain.

| Gate | False passes | Controls retained |
| --- | ---: | ---: |
| Parent snapshot selection | 128/128 | 32/32 |
| Equivocation-aware selection | 0/128 | 32/32 |

All four authority-policy fork families were blocked 32/32: key revocation,
trust-domain assignment, quorum threshold, and key-set membership. Reversing
the complete checkpoint list also produced 0/128 false passes.

## Independent evidence

The independent audit imports zero agnXiv modules. It reconstructs the signed
checkpoint statements, verifies 576 Ed25519 signatures, recomputes the registry
digests for all 160 cases, rebuilds qualifying quorum groups, and reproduces all
128 blocked attacks and 32 accepted controls.

Run:

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_equivocation.py
python research/scripts/audit_authority_registry_checkpoint_equivocation.py
```

Machine-readable evidence is stored in
`research/results/authority-registry-checkpoint-equivocation.json` and
`research/results/authority-registry-checkpoint-equivocation-audit.json`.

## Production consequence

When all disclosed statements are individually valid, input ordering can no
longer determine which same-epoch registry snapshot the hosted gate treats as
authoritative. A disclosed cryptographic split view forces abstention.

## Limitations

This mechanism detects only conflicting qualifying statements presented to the
same gate. It cannot discover withheld statements and does not provide gossip,
transparency-log inclusion, consistency proofs, honest governance, secure key
custody, availability, or threshold-compromise safety. No live checkpoint
service is claimed.
