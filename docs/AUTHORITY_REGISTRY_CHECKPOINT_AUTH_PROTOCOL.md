# Frozen protocol: authenticated registry checkpoints

Status: frozen before implementation and attack execution.

## Threat

The scoped checkpoint API binds an epoch floor to a registry namespace but
does not authenticate the checkpoint object itself. During workflow recovery,
an attacker who can replace configuration can supply a lower floor with the
correct namespace. The old registry and its authority signatures remain
self-consistent, so the gate can reinterpret the forged object as trusted.

## Frozen attack suite

Construct 128 obsolete-but-internally-valid registries across four rollback
families: revoked keys, weakened trust domains, reduced quorum, and removed
keys. For each case, replace the legitimate current checkpoint with an
attacker-created checkpoint carrying the same namespace and the obsolete
epoch.

Thirty-two controls use a current checkpoint signed by the configured
checkpoint authority.

## Proposed mechanism

Add a canonical checkpoint scope containing issuer, key ID, registry
namespace, and minimum epoch. Verify an Ed25519 signature against a dedicated
out-of-band checkpoint-key set before using the namespace or floor. The
checkpoint trust root is deliberately separate from the authority registry it
protects.

Authenticated mode must reject unknown, revoked, malformed, non-Ed25519, and
invalid-signature checkpoint keys. The legacy typed checkpoint remains
available only as the explicitly unauthenticated compatibility path.

## Acceptance criteria

- The current unauthenticated scoped API accepts all 128 forged low-floor
  attacks, documenting the parent boundary.
- Authenticated mode accepts 0/128 forged checkpoints.
- All 32 correctly signed current controls retain their decisive verdict.
- Missing authentication material fails closed when authenticated mode is
  required.
- An independent standard-library audit reproduces all 160 decisions with
  zero agnXiv imports.
- Full tests, Ruff, deterministic evidence, diff checks, and exact-head hosted
  workflows pass.

## Kill criteria

- Any forged checkpoint remains decisive in authenticated mode.
- Any correctly signed current control abstains.
- Authority-registry keys can silently substitute for dedicated checkpoint
  trust roots.
- The signature fails to cover namespace, epoch, issuer, or key ID.

## Claim boundary

Passing establishes checkpoint-object authenticity under configured trusted
keys. It does not deploy a checkpoint distributor, protect the trust-key
configuration channel, prove governance legitimacy, guarantee availability,
or establish a live external reviewer service.
