# Digest-attestation transparency inclusion is now verified

## Result

The frozen 128-case attack matrix passed:

| Attack family | Cases | Signature-only false passes | Inclusion-gate false passes |
|---|---:|---:|---:|
| Missing witness | 32 | 32 | 0 |
| Tampered audit path | 32 | 32 | 0 |
| Wrong leaf index | 32 | 32 | 0 |
| Wrong tree root | 32 | 32 | 0 |

All 32 valid controls remained definitive.  Missing witnesses, prerequisite-
incomplete mode, commitment mismatch, and out-of-range leaf indices fail closed.

## Mechanism

The gate now accepts a versioned transparency witness containing a log
identifier, tree size, leaf index, root digest, and ordered audit path.  It:

1. hashes the canonical witness and requires equality with the digest committed
   inside the signed attestation scope;
2. derives the leaf as
   `SHA256(0x00 || provenance_statement_sha256_bytes)`;
3. verifies the RFC 6962-style audit path with internal nodes
   `SHA256(0x01 || left || right)`;
4. requires the existing scope commitment and Ed25519 authentication modes.

This closes a concrete false-pass boundary: a valid signer can no longer make
an arbitrary witness label sufficient for a decisive scientific verdict.

## Independent verification

The zero-production-import audit independently processed all 160 envelopes. It
canonicalized 160 witnesses, checked 160 signatures, recomputed 160 Merkle
proof outcomes, authenticated exactly the 32 controls, and authenticated none
of the 128 attacks.  Deterministic compressed evidence is emitted for replay.

## Product consequence

Hosted verdict publication can require cryptographic inclusion of the exact
provenance-statement digest in the committed Merkle root.  Ambiguous or
malformed inclusion evidence produces `UNABLE_TO_VERIFY`, preserving the raw
scientific measurements for audit.

## Limitations

This verifies inclusion against the root supplied in the committed witness. It
does not authenticate that root as a real log checkpoint, prove freshness or
append-only consistency, protect log/signing keys, provide hardware attestation,
or demonstrate a live deployment.  Signed log checkpoints and consistency
proofs remain production launch gates.

## Reproduction

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_transparency_inclusion.py
PYTHONPATH=src:research/scripts python research/scripts/audit_authority_registry_checkpoint_transparency_inclusion.py
```
