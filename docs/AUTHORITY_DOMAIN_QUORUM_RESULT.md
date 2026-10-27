# Authority key quorum is not authority-domain quorum

## Result

The parent trusted-registry gate counted distinct `(issuer, key_id)` pairs.
Two registered keys controlled by one administrative domain could therefore
satisfy `minimum_signatures = 2` and produce a definitive hosted verdict.

The corrected registry retains the cryptographic signature threshold and adds
an independent `minimum_trust_domains` threshold. A multi-domain quorum counts
only active, valid signatures whose keys have explicit registry-controlled
domain metadata. Issuer aliases do not create new domains, missing domain
metadata does not contribute, and a revoked key in another domain does not
provide usable diversity.

| Frozen outcome | Exact result |
|---|---:|
| Parent same-control-domain false passes | 128/128 |
| Corrected same-control-domain false passes | 0/128 |
| Corrected two-domain controls definitive | 32/32 |
| Independent attack replays | 128/128 |
| Independent control replays | 32/32 |
| Production imports in independent replay | 0 |

All four adversarial families contributed 32 cases: same-issuer keys, aliased
issuers in one domain, missing domain metadata, and a registry whose nominal
second domain has only a revoked key.

## Preserved negative result

The first frozen replay produced 96/128 parent false passes. Its 32
revoked-domain cases presented a revoked attestation, which the parent gate
already blocks. The protocol amendment preserves that result and changes the
stimulus to two active same-domain attestations plus a non-attesting revoked key
in a second configured domain. This is the actual configuration-versus-usable-
quorum ambiguity; the rerun reproduced 128/128 parent false passes.

## Reproduction

```bash
python research/scripts/verify_authority_domain_quorum.py
python research/scripts/audit_authority_domain_quorum.py
pytest tests/test_authority_registry.py
```

Machine-readable primary and audit evidence is committed at
`research/results/authority-domain-quorum.json` and
`research/results/authority-domain-quorum-audit.json`.

## Product consequence and limits

agnXiv can now distinguish a two-key threshold from a configured two-domain
threshold and abstains when either is unmet. This mechanism does not prove that
domain labels correspond to legally or operationally independent organizations.
It does not establish beneficial ownership, independent key custody, reviewer
competence, unbiased selection, scientific correctness, governance quality, or
deployment of a real external registry. Those remain production launch gates.
