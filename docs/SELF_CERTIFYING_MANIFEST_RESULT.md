# Repository self-certification is not independent verification

## Result

A hosted `verify_spec` job previously allowed one untrusted repository to
supply all of the following:

- the scientific claim and reported value;
- the verification manifest and observation locator;
- the executable that emits the observation;
- the source and dependency environment.

Consequently a command that merely printed its own reported value could cross
every runtime-provenance gate and receive a definitive `VERIFIED` verdict. The
environment was reproducible, but the evidentiary authority was circular.

The hosted runner now labels these bundles `repository_supplied`. The verdict
gate preserves the numeric result and raw decisive verdict as provisional, but
publishes `UNABLE_TO_VERIFY` with the explicit blocker that no independent
verification authority is bound.

## Frozen adversarial result

| Gate | Definitive false passes |
|---|---:|
| Previous environment-only gate | 128/128 |
| Corrected authority-aware gate | 0/128 |

All 128 provisional verdicts and observations were retained for audit. Thirty-two
bundles without the repository-supplied authority label remained decisive,
showing that the correction is scoped to the self-certification boundary.

The independent standard-library checker replayed 128/128 cases, reproduced
the exact case digest
`ed9754868333054a4ccabf898aa6d21929de2b78ba2fa6b1be93661c604a5b23`,
and imported no agnXiv production code.

## Product consequence

Repository-authored manifests remain useful for reproducibility diagnostics:
agnXiv still records their execution identity, observations, provisional
verdict, and blockers. They can no longer independently certify their own
scientific claims in the hosted product.

This changes the semantics of `verify_spec` from definitive verification to
conditional reproduction unless a future independently governed authority
mechanism is added. Auto-planned verification is a separate authority path and
is unchanged by this patch.

## Reproduction

```bash
python research/scripts/verify_self_certifying_manifests.py
python research/scripts/audit_self_certifying_manifests.py
pytest -q
ruff check src tests research/scripts
```

Raw deterministic evidence is in
`research/results/self-certifying-manifests.json`; the independent replay is in
`research/results/self-certifying-manifests-audit.json`.

## Limits and novelty boundary

This is an epistemic authorization rule, not a detector for fabricated code.
It does not establish that auto-planned procedures are scientifically correct,
that repository code is honest, or that a reproduced number supports the
paper's mechanism. It also does not yet provide a trusted third-party manifest
registry, reviewer signatures, or quorum policy.

The general principle that self-attestation is not independent verification is
not novel. The contribution is closing a concrete agnXiv definitive-verdict
false pass while preserving auditable provisional evidence and the existing
runtime-provenance chain.
