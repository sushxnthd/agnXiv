# Checkpoint-authority quorum

## Outcome

The existing authenticated checkpoint path still trusted one configured
checkpoint key.  A compromise of that key therefore allowed a valid
same-namespace low-floor checkpoint to revive an obsolete authority registry.
The frozen parent gate accepted all 128 attacks.

The corrected path requires a configurable quorum of distinct active keys and
distinct checkpoint trust domains over one identical namespace-and-epoch
statement.

| Gate | Obsolete-registry false passes | Current controls |
|---|---:|---:|
| One authenticated checkpoint key | 128/128 | 32/32 |
| Two keys across two trust domains | 0/128 | 32/32 |

All four attack families were blocked 32/32: revocation, trust-domain,
authority-quorum, and key-set rollback.

## Mechanism

`RegistryCheckpointQuorumPolicy` sets independent minimums for signatures and
trust domains.  In quorum mode the gate:

1. verifies every Ed25519 signature under an externally supplied checkpoint
   key;
2. discards unknown, revoked, malformed, and invalid signers;
3. deduplicates `(issuer, key_id)` identities;
4. groups signatures by the exact `(registry_namespace, minimum_epoch)`
   statement;
5. accepts only a group meeting both thresholds; and
6. uses the greatest qualifying floor, so a compromised minority cannot lower
   an independently endorsed current floor.

Legacy singular checkpoints remain available only through the explicitly
singular API.  They cannot silently satisfy `require_registry_checkpoint_quorum`.

## Adversarial falsification

Four targeted attacks all failed closed:

- replaying the same valid signature twice;
- using two distinct keys from one trust domain;
- combining one obsolete-floor signature with one current-floor signature;
- counting a revoked key toward quorum.

The disagreement case is important: signatures are not pooled merely because
they are individually valid.  They must endorse the same statement.

## Independent audit

A standard-library-plus-cryptography auditor imported zero agnXiv modules,
independently verified all 160 Ed25519 signatures, recomputed statement groups,
and reproduced 128/128 blocked attacks and 32/32 accepted controls.

## Reproduction

```bash
PYTHONPATH=src python research/scripts/verify_authority_registry_checkpoint_quorum.py
python research/scripts/audit_authority_registry_checkpoint_quorum.py
pytest -q
```

Machine-readable evidence is stored in
`research/results/authority-registry-checkpoint-quorum.json` and
`research/results/authority-registry-checkpoint-quorum-audit.json`.

## Claim boundary

This mechanism tolerates one compromised checkpoint trust domain only when a
two-domain threshold is correctly configured and at least two genuinely
independent authorities endorse the current floor.  The software cannot prove
organizational independence, secure the initial key-installation channel,
guarantee checkpoint availability, tolerate compromise at or above threshold,
or establish that a live external checkpoint distributor exists.
