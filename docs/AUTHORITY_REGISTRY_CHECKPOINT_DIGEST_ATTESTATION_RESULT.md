# Authority checkpoint digest-attestation result

## Result

The producer-scoped gate accepted all 128 attacks in which the artifact
digests, digest profile, producer identity and measurements, consumer, and
execution remained fixed while the provenance evidence changed.  Producer
measurement binding alone therefore does not bind the evidence asserting
those measurements.

The new attestation-scoped gate produced:

- digest-producer-scoped false passes: **128/128**;
- digest-attestation-scoped false passes: **0/128**;
- matched controls accepted: **32/32**;
- predicate-type substitutions blocked: **32/32**;
- provenance-statement substitutions blocked: **32/32**;
- attestation signer-key substitutions blocked: **32/32**;
- transparency-witness substitutions blocked: **32/32**.

Missing, malformed, mismatched, and incompletely layered attestation modes all
fail closed.  Attestation scope can only be required above producer mode.

## Mechanism

`RegistryCheckpointDigestAttestationScope` binds the exact provenance
predicate, canonical statement digest, signer-key fingerprint, and
transparency inclusion-witness digest above the producer-scoped checkpoint
history.  Replacing any of these independently inspectable dimensions changes
the expected commitment even when every declared producer measurement and
scientific artifact digest remains identical.

The production verdict gate now abstains when the effective provenance scope
does not reproduce the trusted attestation-scoped commitment.  The hosted
production-gate workflow executes and uploads both the producer and
attestation substitution matrices and their independent audits.

## Independent audit

The zero-production-import auditor reconstructed all 160 trusted attestation
commitments and checked 320 source/effective payloads.  Exactly the 32 matched
controls reproduced the trusted effective commitment; none of the 128
substitutions did.

## Bounded claim

This closes provenance-metadata substitution across the four preregistered
dimensions.  It does **not** independently verify the provenance signature,
prove transparency-log inclusion or freshness, attest that the producer
actually executed, protect the trusted commitment store, authenticate the
measurement source, or establish a live deployment.  Those remain explicit
production launch gates.

## Reproduction

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_digest_attestation.py
PYTHONPATH=src python research/scripts/audit_authority_registry_checkpoint_digest_attestation.py
```

The deterministic evidence is stored in
`research/results/authority-registry-checkpoint-digest-attestation.json.gz`
with its summary and independent audit beside it.
