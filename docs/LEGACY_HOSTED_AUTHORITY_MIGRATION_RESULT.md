# Legacy hosted authority migration boundary

## Decisive result

The preserved real-paper artifact from hosted run `40116884857` predates
agnXiv's verification-authority fields. Both scientific bundles therefore
contain real measurements and exact provenance, but no contemporaneous record
that an independent authority selected their verification procedures.

The current service callback was replayed against both exact archived bundles:

| Attack or control | Result |
|---|---:|
| Missing authority rejected | 2/2 |
| `auto_planned` label only rejected | 2/2 |
| Other claim's locator digest rejected | 2/2 |
| Exact locator-binding structural control accepted | 2/2 |
| Measurements preserved | 2/2 |
| Public `UNABLE_TO_VERIFY` verdicts preserved | 2/2 |
| Provisional `CONTRADICTED` comparisons preserved | 2/2 |

The external-paper observations remain 0.504 versus 0.51 and 0.67 versus
0.68. Neither can be silently promoted by omitting authority, attaching an
authority label after the fact, or borrowing the other claim's locator.

## Product consequence

Legacy hosted evidence is importable as auditable provisional evidence, not as
a definitive independently authorized result. A migration must retain the
measurement and abstention while requiring new authority evidence for any
future decisive verdict.

## Independent audit

A standard-library-only checker re-opened the exact 21,398-byte archive,
verified its SHA-256, recomputed both canonical locator digests, checked all
attack outcomes, and imported zero agnXiv production modules.

## Reproduction

```bash
python research/scripts/verify_legacy_hosted_authority_migration.py
python research/scripts/audit_legacy_hosted_authority_migration.py
pytest -q tests/test_service_hardening.py
```

## Limits

The exact-binding control shows that the current callback accepts a correctly
structured current-generation bundle. It does not retroactively establish
that the archived workflow had independent authority. The result also does
not resolve historical environment equivalence or scientific correctness.
