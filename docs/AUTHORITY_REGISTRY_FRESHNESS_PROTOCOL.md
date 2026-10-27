# Frozen protocol: authority-registry rollback freshness

Status: frozen before opening the attack matrix.

## Question

Snapshot-digest binding prevents a signature from being reinterpreted under a
different registry, but it does not prevent a verifier from replaying the
entire old registry together with signatures that bind that old snapshot. Can
an independently anchored monotonic registry epoch close this rollback path
without rejecting evidence issued under the current epoch?

## Threat model

The attacker possesses valid, unexpired authority attestations and the exact
registry snapshot to which they were signed. After governance advances the
registry, the attacker supplies the old snapshot to a verifier that has no
independent freshness floor. Cryptographic signatures and snapshot digests
remain valid. The attack changes no scientific-object fields.

The frozen matrix contains 128 attacks, 32 in each family:

1. `revocation_rollback`: replay an epoch where a now-revoked key was active.
2. `domain_rollback`: replay an epoch before a trust-domain reassignment.
3. `quorum_rollback`: replay an epoch with weaker signature/domain thresholds.
4. `keyset_rollback`: replay an epoch before an authority-key replacement.

Thirty-two controls use the current registry epoch and otherwise identical
valid signatures.

## Proposed mechanism

Add a non-negative monotonic `registry_epoch` to the registry payload, so it is
covered by the existing canonical digest. Let the verifier accept an external
`trusted_minimum_registry_epoch`, maintained independently of the evidence
bundle. A registry below that floor must cause abstention before signature
quorum can authorize a decisive verdict.

The floor is deliberately not inferred from the submitted bundle or registry:
either would let the attacker roll back the claimed floor with the evidence.

## Acceptance criteria

- The parent snapshot-bound gate accepts all 128 exact-snapshot replays.
- The epoch-floor gate accepts 0/128 attacks.
- The corrected gate accepts 32/32 current-epoch controls.
- A standard-library-only audit reproduces all 160 classifications with zero
  agnXiv imports.
- Missing or malformed epochs fail model validation; absence of an externally
  configured floor is reported as no freshness guarantee, not as freshness.
- Full tests, Ruff, deterministic reruns, and the hosted production gate pass.

## Kill criteria

- Any attack remains decisive with the frozen floor.
- Any current-epoch control abstains because of the new check.
- The audit disagrees with the primary matrix.
- The implementation silently treats snapshot-digest equality as freshness.

## Claim boundary

Passing proves rollback resistance relative to an independently maintained
monotonic epoch floor. It does not deploy that checkpoint, prove governance
legitimacy, prevent trust-domain collusion, establish reviewer competence, or
make scientific claims correct.
