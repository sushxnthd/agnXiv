# Canonical immutable image identity gate

## Smallest supported claim

agnXiv now requires container identities to match the canonical Docker content
ID grammar, lowercase `sha256:` followed by exactly 64 hexadecimal characters,
both when reading Docker inspection output and when deciding whether a hosted
scientific verdict may be published.

Malformed identity evidence forces `UNABLE_TO_VERIFY`. The numeric measurement,
expected value, error and raw decision remain available under
`provisional_verdict`.

## Decisive falsification

Before this change, the publication boundary checked only
`value.startswith("sha256:")`. Values such as `sha256:built`, truncated digests,
non-hex payloads and uppercase placeholders therefore satisfied the purported
immutability condition in a valid typed build record.

The frozen matrix injects malformed values independently into the base-image
and built-image fields. This targets the verdict boundary directly instead of
assuming the upstream Docker inspector is infallible.

## Evidence

| Gate | Result |
|---|---:|
| Malformed base/built identity attacks | 210/210 abstained |
| False definitive verdicts | 0 |
| Provisional measurements preserved | 210/210 |
| Canonical positive control | decisive |
| Independent standard-library audit | 210/210 |
| Independent production imports | 0 |
| Full repository regression | 203/203 passed |

The frozen matrix digest is
`a6469812a7ac8ecd40dce6c06c4a77be6b216a87cb718641c03e46ceec81f29d`.

## Enforcement consequence

The same validator is shared by Docker inspection and the hosted verdict gate.
An invalid inspector response fails environment construction. An invalid typed
build record at the independent publication boundary suppresses the public
scientific verdict. This prevents an upstream parsing bug, truncated record or
placeholder from being reinterpreted as immutable runtime evidence.

The production gate now executes the exact adversarial matrix, its independent
checker and the verdict-gate unit contracts on every relevant change.

## Novelty and limits

Content-addressed identifiers and strict digest validation are standard supply
chain security practice. This is not a novel cryptographic construction. The
defensible agnXiv contribution is an adversarially tested scientific-verdict
enforcement boundary that preserves measurements while failing closed on
malformed runtime identity evidence.

This result validates syntax, not existence or authenticity. It does not prove
that an image is still available, that a registry is trustworthy, that the
container isolates hostile code, or that the reconstructed environment matches
the authors' historical runtime. Those remain separate gates.

## Reproduction

```bash
python research/scripts/verify_immutable_image_identity_gate.py
python research/scripts/audit_immutable_image_identity_gate.py
pytest -q tests/test_sandbox.py tests/test_verdict_gate.py
```
