# Frozen protocol: trusted authority registry boundary

Status: frozen before implementation and before adversarial replay.

## Failure under test

The current verdict gate accepts an otherwise decisive bundle when it contains
the string `auto_planned` and a well-formed frozen-locator digest. Those fields
bind an object, but do not authenticate who authorized it. A caller able to
construct a bundle can therefore self-assert both fields.

## Prediction

The old boundary will accept every structurally valid self-asserted authority
case. A corrected strict boundary will require an Ed25519 attestation from a
configured trusted registry key over the exact authority scope:

- manuscript SHA-256;
- repository tree SHA-256;
- claim ID and metric;
- frozen-locator authority-evidence SHA-256;
- issuer, key ID, issuance time, and expiry time.

The attestation must fail closed for an unknown issuer, unknown or revoked key,
invalid signature, expired scope, future-issued scope, or any cross-object
substitution. Registry absence is abstention, never implicit trust.

## Frozen experiment

- 128 self-asserted label-and-digest attacks against the old and strict gates.
- 32 valid trusted-registry controls.
- 32 attacks in each of six families: rogue key, altered locator digest,
  cross-claim replay, cross-manuscript replay, cross-repository replay, and
  expired attestation.
- Independent replay without importing agnXiv production modules.
- Production consequence: the hosted auto-verification path uses the strict
  gate. Until an external registry and its signed attestation are supplied,
  measurements remain available but public verdicts abstain.

## Success and kill criteria

Success requires the old gate to expose the predicted false-pass surface, the
strict gate to issue zero definitive verdicts across every attack family, all
valid controls to remain decisive, and exact independent replay. Any accepted
rogue, replayed, altered, future, expired, or unregistered attestation kills
the implementation and is preserved.

## Bounded claim

This experiment can establish cryptographic registry authentication and exact
object binding. It cannot establish that a registered reviewer is competent,
independent in the social sense, or scientifically correct. Registry policy,
key custody, reviewer selection, and multi-party quorum remain launch gates.
