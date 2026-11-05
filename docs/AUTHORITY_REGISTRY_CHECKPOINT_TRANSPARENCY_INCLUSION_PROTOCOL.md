# Frozen digest-attestation transparency-inclusion matrix

## Status

Frozen before implementation or execution.  The current gate authenticates an
Ed25519-signed digest-attestation scope and commits a SHA-256 label for a
transparency witness, but it does not parse the witness or verify Merkle
inclusion of the provenance statement.

## Frozen attack matrix

Generate 128 signed attacks, 32 per family, plus 32 valid controls:

1. missing inclusion witness;
2. tampered Merkle audit path;
3. wrong leaf index;
4. wrong tree root.

For non-missing attacks, recompute the witness commitment and re-sign the
attestation scope so the existing signature-authentication gate accepts the
case.  The new inclusion gate must accept 0/128 attacks and 32/32 controls.

## Required mechanism

- define a canonical, versioned witness containing log identifier, tree size,
  leaf index, root digest, and ordered SHA-256 audit path;
- require the scope's witness digest to equal SHA-256 of the canonical witness;
- derive the Merkle leaf as `SHA256(0x00 || provenance_statement_sha256_bytes)`;
- verify the RFC 6962-style inclusion path with internal nodes
  `SHA256(0x01 || left || right)`;
- fail closed for missing witnesses, invalid indices, malformed paths,
  commitment mismatch, or root mismatch;
- require the preceding digest-attestation scope and signature-authentication
  modes.

## Independent check and claim boundary

A zero-production-import audit must independently canonicalize all supplied
witnesses, recompute commitments and Merkle roots, and authenticate exactly the
32 controls.  This experiment proves inclusion against the committed root.  It
does not authenticate the log root, prove checkpoint freshness or consistency,
protect the trust store, or establish a live transparency-log deployment.
