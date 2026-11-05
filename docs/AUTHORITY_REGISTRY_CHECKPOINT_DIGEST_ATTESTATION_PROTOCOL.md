# Authority checkpoint digest-attestation protocol

## Status

Frozen before implementation and attack execution.  This continues the single
authority-checkpoint hardening kernel above the committed digest producer.

## Threat

The producer-scoped commitment binds the declared producer identity,
implementation, runtime image, and toolchain measurements, but not the
provenance evidence asserting those measurements.  A workflow can retain every
trusted producer field while substituting the provenance statement, predicate
semantics, attestation signer, or transparency-log witness.  The existing
producer-scoped gate therefore cannot distinguish the trusted attestation from
a different or replayed provenance envelope with identical declared producer
measurements.

## Frozen intervention

Add a typed `RegistryCheckpointDigestAttestationScope` containing:

- the exact provenance predicate type;
- the SHA-256 digest of the canonical provenance statement;
- the SHA-256 fingerprint of the attestation signer key;
- the SHA-256 digest of the transparency-log inclusion witness.

Bind this scope above the digest-producer commitment.  Attestation mode must
require producer mode and fail closed when the scope or trusted commitment is
missing, malformed, mismatched, or incompletely configured.

## Preregistered attack matrix

Generate 32 deterministic attacks for each substitution while holding the
artifact digests, digest profile, producer measurements, consumer, and
execution fixed:

1. provenance predicate substitution;
2. provenance statement substitution;
3. attestation signer-key substitution;
4. transparency-witness substitution.

The digest-producer gate is expected to accept all 128 substitutions.  The
attestation-scoped gate must accept zero, while 32 exactly matched controls
pass.

## Required evidence

- production gate integration and unit checks for every attestation dimension;
- deterministic 128-attack corpus plus 32 controls;
- zero-production-import reconstruction of all trusted and effective
  attestation commitments;
- full regression, lint, deterministic replay, and exact-head hosted status;
- explicit limitation: commitment binding does not independently verify the
  provenance signature, prove transparency-log inclusion or freshness, attest
  actual execution, protect the trusted commitment store, or establish a live
  deployment.
