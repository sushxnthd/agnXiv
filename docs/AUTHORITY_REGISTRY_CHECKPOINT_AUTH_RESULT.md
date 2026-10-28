# Authenticated authority-registry checkpoints

## Outcome

The frozen attack confirmed that namespace binding alone does not authenticate
the checkpoint object. The parent scoped API accepted all 128 forged
same-namespace low-floor checkpoints. The new authenticated path accepted
none, while preserving every correctly signed current control.

| Gate | Forged rollback accepted | Current controls accepted |
|---|---:|---:|
| Scoped but unauthenticated checkpoint | 128/128 | 32/32 |
| Dedicated-key authenticated checkpoint | 0/128 | 32/32 |

The attacks cover obsolete revocation, trust-domain, quorum, and key-set
registries. Each obsolete registry and its scientific authority signatures is
internally valid. The attack changes only the trusted epoch statement from 73
to 41 while retaining its original signature.

## Mechanism

`RegistryCheckpointScope` canonically binds:

1. checkpoint issuer;
2. checkpoint key ID;
3. authority-registry namespace; and
4. minimum registry epoch.

`SignedRegistryCheckpoint` carries an Ed25519 signature over that exact
canonical payload. Verification uses a dedicated
`TrustedRegistryCheckpointKey` set supplied outside the protected authority
registry. This separation prevents an obsolete registry from authorizing its
own rollback checkpoint.

Authenticated mode rejects unknown, revoked, malformed, non-Ed25519, and
invalid-signature checkpoint keys. A raw `TrustedRegistryCheckpoint` cannot
satisfy `require_authenticated_registry_checkpoint`; it remains only the
explicit compatibility path.

## Evidence

- Parent false passes: 128/128.
- Authenticated false passes: 0/128.
- Signed current controls: 32/32.
- All four attack families: 32/32 blocked.
- Independent standard-library audit: 160/160 decisions reproduced with zero
  agnXiv imports.
- Evidence reproduced byte-for-byte.

## Reproduction

```bash
PYTHONPATH=src python research/scripts/verify_authority_registry_checkpoint_auth.py
python research/scripts/audit_authority_registry_checkpoint_auth.py
pytest -q
```

Machine-readable evidence is stored in
`research/results/authority-registry-checkpoint-auth.json` and
`research/results/authority-registry-checkpoint-auth-audit.json`.

## Production consequence

Deployments can now require cryptographic checkpoint provenance rather than
trusting configuration-shaped data solely because it has the correct
namespace. The checkpoint public keys must come from a separately protected
configuration channel.

## Claim boundary

This establishes object authenticity under configured checkpoint trust keys.
It does not deploy a checkpoint distributor, authenticate the channel that
installs those keys, prove reviewer or operator independence, guarantee that
the issuer advances epochs honestly, establish governance legitimacy, or
claim a live production service.
