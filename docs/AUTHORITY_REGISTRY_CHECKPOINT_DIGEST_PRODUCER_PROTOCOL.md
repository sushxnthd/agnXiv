# Authority checkpoint digest-producer protocol

## Status

Frozen before implementation and attack execution.  This continues the single
authority-checkpoint hardening kernel.

## Threat

The digest-profile commitment binds declared derivation semantics, but not the
producer that executed them.  A workflow can retain the trusted profile and
all artifact SHA-256 values while silently replacing the digest producer, its
implementation, runtime image, or toolchain.  The existing profile-scoped gate
therefore cannot distinguish the trusted producer from a semantically
different implementation that reports the same values.

## Frozen intervention

Add a typed `RegistryCheckpointDigestProducerScope` containing:

- a nonempty producer identity;
- the SHA-256 measurement of the producer implementation;
- a canonical immutable runtime image digest;
- the SHA-256 digest of the complete toolchain manifest.

Bind this scope above the digest-profile commitment.  Producer mode must
require profile mode and fail closed when the scope or trusted commitment is
missing, malformed, mismatched, or incompletely configured.

## Preregistered attack matrix

Generate 32 deterministic attacks for each substitution while holding the
artifact digests, artifact scope, profile, consumer, and execution fixed:

1. producer identity substitution;
2. producer implementation substitution;
3. runtime image substitution;
4. toolchain manifest substitution.

The digest-profile gate is expected to accept all 128 substitutions.  The
producer-scoped gate must accept zero, while 32 exactly matched controls pass.

## Required evidence

- production gate integration and unit checks for every producer dimension;
- deterministic 128-attack corpus plus 32 controls;
- zero-production-import reconstruction of all trusted and effective producer
  commitments;
- full regression, lint, deterministic replay, and exact-head hosted status;
- explicit limitation: commitment binding does not prove that the measured
  producer actually executed, authenticate the measurement source, provide a
  trusted execution environment, or establish a live deployment.
