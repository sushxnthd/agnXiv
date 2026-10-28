# Authority-registry checkpoint scope binding

## Result

A bare integer freshness floor prevents rollback only if the verifier already
knows which registry that integer belongs to. In a multi-registry verifier, the
parent gate accepted every frozen configuration in which a floor from one
workflow or governance namespace was reused for another registry.

agnXiv now supports a typed external checkpoint that binds the monotonic floor
to a stable registry namespace. When scoped freshness is required, namespace
mismatch or a missing scoped checkpoint causes abstention before signer quorum
can authorize a decisive verdict.

| Frozen outcome | Exact result |
|---|---:|
| Bare-floor parent wrong-scope false passes | 128/128 |
| Scoped-checkpoint wrong-scope false passes | 0/128 |
| Matched-namespace controls definitive | 32/32 |
| Independent attack replays | 128/128 |
| Independent control replays | 32/32 |
| agnXiv imports in independent replay | 0 |

The four pre-registered families contributed 32 attacks each: staging to
production, tenant to tenant, paper track to release gate, and benchmark to
external audit. Every registry, signature, scientific-object binding, epoch,
and snapshot digest remained valid. Only the external checkpoint namespace was
wrong.

## Mechanism

`TrustedAuthorityRegistry` version 3 adds `registry_namespace` to the canonical
digest-bound payload. `TrustedRegistryCheckpoint` contains the same namespace
and a non-negative `minimum_registry_epoch`.

The corrected gate checks both dimensions:

1. the checkpoint namespace must equal the registry namespace; and
2. the registry epoch must meet the checkpoint floor.

The previous integer-only argument remains available as an explicitly
unscoped compatibility path. It is not silently treated as scoped evidence.
Callers that require checkpoint scope but omit the typed checkpoint fail
closed. Empty namespaces and negative floors fail model validation.

## Reproduction

```bash
python research/scripts/verify_authority_registry_checkpoint_scope.py
python research/scripts/audit_authority_registry_checkpoint_scope.py
pytest tests/test_authority_registry.py
```

Primary and independent evidence is committed at
`research/results/authority-registry-checkpoint-scope.json` and
`research/results/authority-registry-checkpoint-scope-audit.json`.

## Product consequence and limits

This closes cross-registry freshness-floor confusion for callers that require
the scoped checkpoint API. It is directly relevant to multi-tenant services,
staging/production separation, and workflow-scoped environment recovery.

agnXiv does not claim that a checkpoint distributor or external reviewer
registry is deployed. The mechanism does not authenticate checkpoint delivery,
establish governance legitimacy, prevent authority collusion, measure reviewer
competence, or make scientific claims correct. A caller that deliberately uses
the legacy bare floor retains its documented unscoped limitation.
