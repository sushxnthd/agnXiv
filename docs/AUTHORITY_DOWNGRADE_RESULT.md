# Missing authority is not independent authority

## Result

The previous self-certification correction blocked a decisive hosted verdict
only when a bundle was explicitly labelled `repository_supplied`. The bundle
schema still permitted the authority field to be absent, and the gate treated
that absence as trusted. Removing one field from an otherwise identical
self-certifying result therefore restored `VERIFIED`, `PARTIALLY_VERIFIED`, or
`CONTRADICTED` at the publication boundary.

The gate now admits a decisive hosted verdict only with explicit
`auto_planned` authority. Missing authority and `repository_supplied` authority
both fail closed while preserving the raw verdict and observations as
provisional evidence.

The hosted runner stamps every zero-manifest bundle, including additional
claims, as `auto_planned` before gating. The repository-spec path continues to
stamp `repository_supplied`. The service callback independently checks that
the authority matches the requested job mode, so an authenticated worker
cannot change the authority label or delete it without rejection.

## Frozen adversarial result

| Boundary | Result |
|---|---:|
| Missing-authority downgrade attacks under old gate | 128/128 definitive |
| Missing-authority attacks under corrected gate | 0/128 definitive |
| Provisional verdict and observation retained | 128/128 |
| Explicit auto-planned controls preserved | 32/32 |
| Independent stdlib-only replays | 160/160 |

The attacks cover all three decisive verdict classes. Mode-binding unit tests
also reject both an auto-verification result with missing authority and a
repository-spec result falsely claiming `auto_planned`.

## Product consequence

Authority provenance is now positive evidence rather than a blacklist. A
bundle cannot become more trusted by deleting metadata. This closes the
downgrade path at both the scientific verdict gate and the hosted service
ingress, while leaving the provisional evidence available for audit.

## Reproduction

```bash
python research/scripts/verify_authority_downgrade.py
python research/scripts/audit_authority_downgrade.py
pytest -q
ruff check src tests research/scripts
```

Raw deterministic evidence is stored in
`research/results/authority-downgrade.json`; the independent replay is in
`research/results/authority-downgrade-audit.json`.

## Limits and novelty boundary

Fail-closed provenance and explicit authorization are established security
principles. The contribution claimed here is the discovery, adversarial
reproduction, and closure of a concrete agnXiv scientific-verdict downgrade,
not a new authorization primitive.

The `auto_planned` label records which agnXiv workflow selected the procedure;
it does not prove that the procedure is scientifically correct, independent of
the paper authors, or sufficient to establish mechanism. Trusted third-party
reviewer authority, signatures tied to reviewer identity, quorum policy, and
external paper reproduction remain separate launch requirements.
