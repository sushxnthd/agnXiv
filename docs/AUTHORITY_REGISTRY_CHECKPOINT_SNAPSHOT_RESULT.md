# Checkpoint-bound authority-registry snapshots

## Result

The authenticated checkpoint quorum previously signed only a registry
namespace and minimum epoch. A different authority-registry snapshot could
therefore reuse a legitimate quorum statement when it carried the same
namespace and epoch.

The frozen matrix confirmed the vulnerability and the correction:

| Gate | Same-epoch fork false passes | Endorsed controls |
|---|---:|---:|
| Namespace-and-epoch quorum | 128/128 | 32/32 |
| Snapshot-digest quorum | 0/128 | 32/32 |

All four policy families were blocked 32/32: key revocation, trust-domain
assignment, quorum configuration, and key-set membership.

## Mechanism

`RegistryCheckpointScope` can now carry `authority_registry_sha256`, the
canonical SHA-256 digest of the complete authority-registry object. Callers
that set `require_registry_checkpoint_snapshot=True` require a qualifying
multi-domain quorum whose signed digest exactly matches the supplied registry.
Missing, malformed, or mismatched digest binding causes conservative
abstention.

The original floor-only behavior remains explicit for backward compatibility.
It is not described as snapshot-consistent.

## Independent audit

The independent audit imports zero agnXiv modules. It reconstructed all 160
pairs of registry digests, verified 320 Ed25519 checkpoint signatures, rebuilt
the quorum groups, and reproduced all 128 blocked attacks and 32 accepted
controls.

## Reproduction

```bash
PYTHONPATH=src python research/scripts/verify_authority_registry_checkpoint_snapshot.py
python research/scripts/audit_authority_registry_checkpoint_snapshot.py
```

Machine-readable evidence is stored in
`research/results/authority-registry-checkpoint-snapshot.json` and
`research/results/authority-registry-checkpoint-snapshot-audit.json`.

## Limitations

Snapshot binding does not establish honest checkpoint governance, secure
initial key installation, availability, threshold-compromise safety, or
append-only consistency between successive epochs. It does not prove that a
checkpoint distributor is deployed. It proves only that a valid quorum
statement cannot be detached from the exact registry snapshot it endorsed.
