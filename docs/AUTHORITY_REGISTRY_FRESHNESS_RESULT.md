# Authority-registry rollback freshness gate

## Result

Exact snapshot binding was necessary but not sufficient. A verifier could
replay a complete old registry together with still-valid signatures that bound
that old snapshot. Every digest and signature remained internally consistent,
so the prior gate accepted all 128 frozen rollback attacks.

agnXiv now includes a non-negative monotonic `registry_epoch` in the canonical
registry payload and can require an independently supplied
`trusted_minimum_registry_epoch`. Registries below that floor cause abstention
before their otherwise-valid signer quorum can authorize a decisive verdict.

| Frozen outcome | Exact result |
|---|---:|
| Snapshot-bound parent false passes | 128/128 |
| Epoch-floor false passes | 0/128 |
| Current-epoch controls definitive | 32/32 |
| Independent attack replays | 128/128 |
| Independent control replays | 32/32 |
| agnXiv imports in independent replay | 0 |

The four pre-registered families each contributed 32 attacks: revocation,
trust-domain, quorum, and key-set rollback. The scientific object, signatures,
validity windows, and supplied registry digest were all valid. Only the
independently trusted epoch floor distinguished an obsolete snapshot from the
current policy.

## Mechanism

`TrustedAuthorityRegistry` version 2 adds `registry_epoch`. Because the epoch
is inside the existing canonical registry digest, it cannot be edited without
invalidating every bound authority signature.

The freshness floor is a separate verifier input. It is never inferred from
the submitted evidence or registry because an attacker could replay either
along with the obsolete snapshot. Callers that require freshness but omit the
floor fail closed with an explicit blocker. Negative epochs fail model
validation, and current-epoch evidence retains its original verdict.

## Reproduction

```bash
python research/scripts/verify_authority_registry_freshness.py
python research/scripts/audit_authority_registry_freshness.py
pytest tests/test_authority_registry.py
```

Raw primary and independent evidence is committed at
`research/results/authority-registry-freshness.json` and
`research/results/authority-registry-freshness-audit.json`.

## Product consequence and limits

The verification boundary can now enforce monotonic authority-policy progress:
once an operator or external checkpoint advances the trusted floor, evidence
cannot reactivate old keys, domains, or thresholds by replaying an internally
valid historical registry.

This is rollback resistance **relative to an independently maintained floor**.
agnXiv does not claim that such a checkpoint is deployed. If a caller does not
require freshness or supplies a stale floor, the old snapshot remains
acceptable. The mechanism does not establish governance legitimacy,
independent key custody, reviewer competence, unbiased reviewer selection,
scientific correctness, or a live production deployment.
