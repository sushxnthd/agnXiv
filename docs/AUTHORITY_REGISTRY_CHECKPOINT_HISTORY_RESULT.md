# Persisted checkpoint-history consistency

## Result

The disclosed-equivocation gate only compared quorum statements supplied in one
invocation. A server could first show a client one valid registry snapshot and
later present only a conflicting same-namespace, same-epoch quorum. With the
earlier statement withheld, the parent gate accepted all 128 frozen attacks.

The corrected gate accepts an explicit persisted signed-observation history. It
authenticates historical statements under the same checkpoint-key trust root
and quorum policy, then rejects conflicting qualifying digests at the same
namespace and epoch across current and historical views.

| Gate | Sequential split-view false passes | Matching-history controls | Prior-epoch controls |
|---|---:|---:|---:|
| Current quorum only | 128/128 | 32/32 | 32/32 |
| History-consistent quorum | 0/128 | 32/32 | 32/32 |

All four policy-fork families were blocked 32/32. Reversing current and
historical signature order produced zero false passes. The gate also abstains
when required history is omitted, when historical signatures are invalid, or
when a historical quorum is supplied without a current quorum.

The zero-agnXiv-import audit independently verified 768 Ed25519 signatures,
reconstructed 192 registry digests and quorum sets, and reproduced all 128
attacks plus 64 controls.

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_history.py
python research/scripts/audit_authority_registry_checkpoint_history.py
```

Evidence is stored in the deterministic raw artifact
`research/results/authority-registry-checkpoint-history.json.gz`, its
human-readable summary, and the independent audit JSON.

## Limitations

This detects conflicts only among signed observations retained and supplied by
the trusted workflow. It does not make history append-only, detect deleted
observations, discover views never observed, provide cross-client gossip, prove
transparency-log inclusion or consistency, secure checkpoint-key custody,
guarantee availability, or claim a deployed checkpoint service.
