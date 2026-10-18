# Issuer Key Rotation Runbook

AgnXiv signs verification statements with the current Ed25519 issuer key. Previously issued statements must remain independently verifiable after rotation.

## Configuration

- `AGNXIV_ISSUER_PRIVATE_KEY_B64` — base64-encoded current Ed25519 private PEM. Only this key signs new statements.
- `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64` — comma-separated base64-encoded Ed25519 public PEMs retained for verification of historical statements.
- `GET /v1/issuer` — publishes the current key plus retained previous public keys and stable key IDs.

Private keys must never be placed in the repository, logs, database, job payloads, GitHub artifacts, or previous-key configuration.

## Zero-downtime rotation

1. Generate a new Ed25519 keypair offline.
2. Record the current public key from `GET /v1/issuer` and verify its key ID against an already signed verification record.
3. Before changing the signer, add the current public key to `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64` and deploy. Confirm both the current key and all older retained keys appear from `GET /v1/issuer`.
4. Replace `AGNXIV_ISSUER_PRIVATE_KEY_B64` with the new private key and deploy.
5. Confirm readiness is green and `GET /v1/issuer` reports the new key as `current` while the old key remains `previous`.
6. Run one signed canary verification and verify the DSSE envelope offline against the new public key.
7. Retain old public keys for at least as long as any AgnXiv evidence record that may reference them. Public keys are not secrets; retaining them is expected.
8. Remove a retired public key only after the associated evidence retention window has expired or a permanent archival key registry contains it.

## Emergency compromise procedure

If the active private key is suspected compromised, stop hosted signing, rotate immediately, publish the retired key ID as compromised in the incident record, and do not re-sign historical evidence as though it were originally produced by the replacement key. Verification statements remain immutable evidence with their original key IDs.

## Validation

Production readiness fails if the current private key cannot be parsed, a rollover public key is invalid, or a previous key duplicates the current key ID. The issuer endpoint keeps backward-compatible top-level `key_id` and `public_key_pem` fields while also publishing the full `agnxiv.issuer-keyset/1` keyset.
