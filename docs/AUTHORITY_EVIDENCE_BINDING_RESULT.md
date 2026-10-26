# Auto-planned authority is now bound to its exact evidence

## Result

The hosted callback previously validated an `auto_planned` verification bundle
and a frozen discovery locator as separate well-formed objects. It did not
prove that the locator accompanying a bundle was the locator that authorized
that bundle's observation. A callback could therefore pair a decisive bundle
created under locator A with distinct locator B and retain a definitive
`VERIFIED` or `CONTRADICTED` verdict.

Each auto-planned bundle now contains `authority_evidence_sha256`, the canonical
JSON SHA-256 of its exact frozen locator. The hosted runner establishes this
one-to-one binding before verdict gating. The verdict gate abstains if the
commitment is missing or malformed, and the service callback independently
recomputes it for the primary bundle and every additional verification. The
signed in-toto predicate exposes both the authority kind and evidence digest.

## Frozen adversarial result

| Boundary | Result |
|---|---:|
| Cross-locator substitutions accepted by the old boundary | 128/128 |
| Cross-locator substitutions accepted after correction | 0/128 |
| Matching authority-evidence controls retained | 32/32 |
| Independent stdlib-only replays | 160/160 |
| Production imports in independent replay | 0 |

The attack protocol was committed before implementation. Cases vary claim,
metric, regular expression, label, and discovery-output digest. Every source
and substituted locator has a distinct canonical digest.

## Product consequence

`auto_planned` is no longer a free-floating label. A decisive verification
statement commits to the exact locator evidence that selected its observation,
and the publication service rejects cross-object substitution even from an
otherwise authenticated worker result. Missing commitments remain visible as
provisional evidence but cannot publish a decisive scientific verdict.

## Reproduction

```bash
python research/scripts/verify_authority_evidence_binding.py
python research/scripts/audit_authority_evidence_binding.py
pytest -q
ruff check src tests research/scripts
```

Raw deterministic evidence is stored in
`research/results/authority-evidence-binding.json`; the independent replay is
in `research/results/authority-evidence-binding-audit.json`.

## Limits and novelty boundary

Canonical hashing and provenance binding are established security techniques.
The bounded contribution is discovery, adversarial reproduction, and closure
of this concrete cross-object scientific-verdict vulnerability.

This result does **not** establish that an auto-planned procedure is
scientifically correct or independent of the paper authors. It also does not
establish worker integrity, sandbox isolation, dependency fidelity, reviewer
identity, registry trust, or quorum. Trusted third-party authority and real
external-paper reproduction remain open launch gates.
