# Authority checkpoint digest-attestation authentication protocol

## Status

Frozen before implementation and attack execution.  This continues the single
authority-checkpoint hardening kernel, changing the experiment from another
metadata commitment to cryptographic authentication.

## Threat

The attestation-scoped commitment binds the declared provenance predicate,
statement digest, signer-key fingerprint, and transparency witness, but it does
not verify a signature from that signer.  A workflow can present the trusted
metadata while omitting the signature, supplying malformed bytes, signing with
an untrusted key, or replaying a valid trusted-key signature over another
attestation scope.  The current gate cannot distinguish these forgeries from
an authenticated provenance statement.

## Frozen intervention

Add a typed signed digest-attestation envelope.  Canonically serialize the
complete `RegistryCheckpointDigestAttestationScope`, verify an Ed25519
signature with a separately trusted public key, and require the SHA-256
fingerprint of that key to equal the fingerprint already committed in the
scope.  Authentication mode must require attestation-scope mode and fail
closed on missing, malformed, mismatched, non-Ed25519, or invalid signatures.

## Preregistered attack matrix

Generate 32 deterministic cases for each attack while preserving the trusted
attestation commitment and all upstream artifact, profile, and producer data:

1. missing signature envelope;
2. malformed base64 signature;
3. signature by an untrusted Ed25519 key while declaring the trusted key;
4. valid trusted-key signature replayed from a different attestation scope.

The metadata-only attestation gate is expected to accept all 128 attacks.  The
authenticated gate must accept zero, while 32 valid trusted-key controls pass.

## Required evidence

- production verdict-gate integration and canonical key fingerprinting;
- deterministic 128-attack corpus plus 32 controls;
- zero-production-import signature verification and payload replay;
- full regression, lint, deterministic replay, and exact-head hosted status;
- explicit limitation: signature authentication does not prove transparency-
  log inclusion or freshness, protect the signing key or trust store, provide
  hardware attestation, prove actual producer execution, or establish a live
  deployment.
