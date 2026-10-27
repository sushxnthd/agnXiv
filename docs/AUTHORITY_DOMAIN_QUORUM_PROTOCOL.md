# Frozen protocol: independent authority-domain quorum

Protocol frozen before implementation. Parent commit:
`2752bca6ba587370340d0e197d16a452dc2b83b3`.

## Question

Can `minimum_signatures = 2` be satisfied by two registered keys controlled by
one authority domain, causing a cryptographic key threshold to be mistaken for
independent authority?

## Pre-registered prediction

The current registry gate counts distinct `(issuer, key_id)` pairs. It will
therefore accept all 128 frozen same-domain, two-key attacks. A corrected gate
will preserve the signature threshold but additionally require two explicitly
configured, distinct trust domains. It will reject all 128 attacks and accept
all 32 controls signed by two active keys in two distinct trust domains.

## Frozen cases

All cases bind signatures to the exact manuscript, repository tree, claim,
metric, locator digest, and validity window.

- 32 same issuer, two keys, one trust domain;
- 32 aliased issuer strings, two keys, one trust domain;
- 32 one explicit domain plus one key missing domain metadata;
- 32 two configured domains where the second key is revoked;
- 32 positive controls with two active keys in two explicit domains.

The domain-aware registry is configured with `minimum_signatures = 2` and
`minimum_trust_domains = 2`. Missing explicit domain metadata cannot contribute
to a multi-domain quorum. Domain labels are supplied by the trusted registry,
not by the attestation.

## Success and kill criteria

Success requires:

1. the domain-blind parent gate accepts 128/128 attacks;
2. the corrected gate produces zero definitive false passes across 128 attacks;
3. the corrected gate accepts 32/32 positive controls;
4. an independent replay that imports no agnXiv code agrees exactly;
5. focused tests, the full suite, lint, and deterministic reruns pass.

Kill or reformulate the kernel if any attack remains definitive, any positive
control abstains, the independent replay disagrees, or a result cannot be
reproduced from committed inputs.

## Bounded claim

Passing this protocol establishes only that a configured threshold requires
cryptographically valid signatures from distinct registry-defined trust
domains. It does not establish real organizational independence, beneficial
ownership, key custody, reviewer competence, reviewer selection, scientific
correctness, governance, or a deployed external registry.
