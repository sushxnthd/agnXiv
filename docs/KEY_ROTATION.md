# AgnXiv issuer key rotation

AgnXiv signs hosted verification statements with an active Ed25519 issuer key. Key rotation must preserve the public keys needed to validate historical DSSE evidence without leaving retired private keys in the running service.

## Runtime configuration

- `AGNXIV_ISSUER_PRIVATE_KEY_B64` contains the base64-encoded PEM for the **active private key**. Only this key signs new records.
- `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64` is a comma-separated list of base64-encoded PEM **public keys** from routine rotations. These remain trusted for historical records.
- `AGNXIV_ISSUER_REVOKED_PUBLIC_KEYS_B64` is a comma-separated list of base64-encoded PEM public keys that must remain discoverable but are no longer trusted, for example after suspected private-key compromise.

The service publishes the complete public keyring at `GET /v1/issuer`. Each key is labeled `active`, `retired`, or `revoked`, together with whether it may sign new records and whether historical signatures remain trusted.

## Routine rotation procedure

1. Generate a new Ed25519 keypair with `agnxiv keygen`. Keep the private key outside source control and CI artifacts.
2. Read the current active public key from `GET /v1/issuer` and preserve that public PEM.
3. In one deployment change:
   - replace `AGNXIV_ISSUER_PRIVATE_KEY_B64` with the new private key;
   - append the former active **public** key to `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64`.
4. Deploy and require `/readyz` to pass. Duplicate, malformed, or non-Ed25519 historical keys cause readiness to fail closed.
5. Confirm `/v1/issuer` reports the new key as `active` and the previous key as `retired`.
6. Produce a new signed verification and confirm its DSSE `keyid` matches the new active key ID.
7. Verify at least one pre-rotation DSSE record with the retired public key.
8. Remove the old private key from runtime secrets after cutover. Retain its public key for at least as long as any signed AgnXiv record that references it.

## Suspected compromise

Do not place a compromised key in the ordinary retired set. Move its public key to `AGNXIV_ISSUER_REVOKED_PUBLIC_KEYS_B64` and rotate to a new active private key. The issuer endpoint will continue exposing the compromised key so old evidence remains auditable, but it is explicitly marked `revoked` and `trusted_for_historical_records=false`.

If the active private key may have been exposed, prefer a forward rotation to a fresh key over silently reactivating a prior key. Preserve incident timing separately so downstream verifiers can determine which historical signatures require review.

## Rollback

During a planned rotation, retain the prior private key only in the secure secret-management system until the new deployment has passed readiness and signature checks. If the cutover fails before compromise is suspected, the prior active key may be restored together with the pre-rotation keyring. After successful cutover, normal rollback should roll the application back without rolling the issuer identity backward.

## Verification contract

The stable key ID is SHA-256 over the raw Ed25519 public key bytes. The legacy top-level `key_id`, `algorithm`, and `public_key_pem` fields in `/v1/issuer` continue to describe the active key; `schema_version=agnxiv.issuer/2` and `keys[]` provide rollover metadata.
