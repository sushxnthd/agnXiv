# Digest-attestation authentication result

## Result

The attestation-scoped metadata gate accepted all 128 attacks that preserved
the trusted scope and upstream commitments while removing or forging the
cryptographic envelope.  A committed signer fingerprint therefore does not by
itself authenticate the provenance statement.

The new Ed25519-authenticated gate produced:

- metadata-scoped false passes: **128/128**;
- authenticated false passes: **0/128**;
- valid trusted-key controls accepted: **32/32**;
- missing signatures blocked: **32/32**;
- malformed base64 signatures blocked: **32/32**;
- untrusted-key signatures blocked: **32/32**;
- valid signatures replayed from another attestation scope blocked: **32/32**.

Missing keys, missing signatures, prerequisite-incomplete modes, and public
keys whose canonical fingerprint differs from the committed signer all fail
closed.

## Mechanism

The gate canonically serializes the complete
`RegistryCheckpointDigestAttestationScope`, verifies its Ed25519 signature
against a separately trusted public key, and computes the key fingerprint from
DER SubjectPublicKeyInfo rather than trusting a caller-supplied identifier.
The computed fingerprint must equal the signer fingerprint already bound into
the attestation commitment.

This prevents a workflow from declaring the trusted signer while supplying no
signature, garbage, a rogue-key signature, or a valid trusted-key signature
over different provenance evidence.  The hosted production-gate workflow now
executes and uploads the authentication matrix and independent audit.

## Independent audit

The zero-production-import audit independently canonicalized all 160 scopes,
recomputed all 160 key fingerprints, and attempted verification of every
envelope.  Exactly the 32 matched controls authenticated; none of the 128
attacks did.

## Bounded claim

This establishes signature authenticity for the committed provenance scope
under the configured Ed25519 public key.  It does **not** prove transparency-
log inclusion or freshness, protect the signing key or trusted key store,
provide hardware-backed attestation, prove that the digest producer actually
executed, or establish a live deployment.  Those remain production launch
gates.

## Reproduction

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_digest_attestation_auth.py
PYTHONPATH=src python research/scripts/audit_authority_registry_checkpoint_digest_attestation_auth.py
```
