# Hosted issuer key rotation

AgnXiv signs hosted verification statements with one active Ed25519 issuer key.
Rotation must preserve verification of historical DSSE envelopes without retaining
retired private keys.

## Configuration

- `AGNXIV_ISSUER_PRIVATE_KEY_B64` contains the base64-encoded active Ed25519
  private PEM. Only this key signs new hosted statements.
- `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64` is an optional comma-separated list
  of base64-encoded retired Ed25519 public PEM keys.
- `GET /v1/issuer` publishes the active key and the complete public verification
  keyring as `agnxiv.issuer/1`. Historical verifiers select the public key by the
  DSSE signature `keyid`.

Retired private keys must not be stored in the service after the rotation is
confirmed.

## Rotation procedure

1. Generate a new Ed25519 keypair offline with `agnxiv keygen`.
2. Fetch `GET /v1/issuer` from the currently healthy service and archive the
   response with the deployment record.
3. Base64-encode the current active **public** PEM and append it to
   `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64`.
4. Replace `AGNXIV_ISSUER_PRIVATE_KEY_B64` with the new private PEM encoded as
   base64. Do not remove any still-required retired public key.
5. Deploy the configuration atomically.
6. Require `/readyz` to return ready. Read `/v1/issuer` and confirm:
   - `active_key_id` is the new key identifier;
   - exactly one key has `status: active`;
   - the previous key remains present with `status: retired`;
   - no private key material is exposed.
7. Create one signed canary verification and confirm its DSSE `keyid` equals
   the new `active_key_id`.
8. Re-verify at least one archived envelope signed by each retired key against
   the corresponding entry in `verification_keys`.
9. Destroy or escrow the retired private key according to incident-recovery
   policy. The hosted service must retain only its public key.

## Rollback

If the new signer fails before new statements have been relied upon, restore the
previous private key as active and keep the attempted new public key in the
verification keyring if any statement was signed with it.

If new statements were already issued, never remove the new public key during
rollback. A rollback may change which private key is active, but the public
keyring must remain a superset of every key needed to verify retained records.

## Removal rule

A retired public key may be removed only after every verification record and
artifact covered by the retention policy that references its `keyid` has
expired or been durably re-attested under a supported key. Until AgnXiv has a
final long-term artifact retention policy, retired public keys should be kept.
