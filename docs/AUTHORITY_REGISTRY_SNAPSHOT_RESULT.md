# Authority signatures now bind their exact registry snapshot

## Result

The parent authority payload committed to the signer and scientific object but
not to the registry policy used to interpret the signature. The same valid
signatures could therefore be evaluated under a replacement registry that
changed trust-domain assignments, revocation state, or quorum thresholds.

agnXiv now computes a canonical SHA-256 digest over the complete trusted
authority registry and includes it in the signed authority scope. The verifier
recomputes the digest for the supplied registry and abstains unless the two are
identical.

| Frozen outcome | Exact result |
|---|---:|
| Parent substituted-registry false passes | 128/128 |
| Corrected substituted-registry false passes | 0/128 |
| Exact-registry controls definitive | 32/32 |
| Independent attack replays | 128/128 |
| Independent control replays | 32/32 |
| agnXiv imports in independent replay | 0 |

Each of the four pre-registered families contributed 32 cases: trust-domain
remapping, revocation rollback, quorum downgrade, and a combined key-policy
swap. All signatures remained cryptographically valid; only the unsigned
interpretive registry changed.

## Mechanism

`AuthorityScope` version 2 contains `authority_registry_sha256`. The digest
covers the registry schema, signature threshold, trust-domain threshold, public
key records, domain assignments, and active/revoked status values using stable
canonical JSON. This turns registry policy from ambient verifier configuration
into signed evidence.

Missing digests and any changed policy field fail closed. Exact-registry
controls retain their decisive verdicts.

## Reproduction

```bash
python research/scripts/verify_authority_registry_snapshot.py
python research/scripts/audit_authority_registry_snapshot.py
pytest tests/test_authority_registry.py
```

Raw primary and independent evidence is committed at
`research/results/authority-registry-snapshot.json` and
`research/results/authority-registry-snapshot-audit.json`.

## Product consequence and limits

An exported bundle now identifies the exact authority policy under which it was
approved; a consumer cannot silently relabel signers, reactivate a revoked key,
or lower quorum requirements while reusing the signature.

This is snapshot integrity, not registry governance or freshness. A verifier
can still deliberately choose the wrong registry before signatures are issued,
replay an old but exactly bound snapshot when no external freshness rule exists,
or trust false domain labels. The mechanism does not prove independent key
custody, reviewer competence, unbiased selection, scientific correctness, or a
live external registry deployment.
