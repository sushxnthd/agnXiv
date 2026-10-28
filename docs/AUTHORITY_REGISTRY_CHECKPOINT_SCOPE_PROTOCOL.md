# Frozen protocol: authority-registry checkpoint scope

Status: frozen before opening the attack matrix.

## Question

The rollback gate accepts a bare integer freshness floor. In a verifier that
operates multiple authority registries, that integer carries no stable registry
identity. Can a checkpoint from one workflow or governance namespace be wired
to another registry and still authorize a decisive verdict?

## Threat model

The supplied registry, evidence signatures, snapshot digest, epoch, and
scientific-object bindings are all internally valid. The configuration error
is external: the verifier supplies a freshness floor copied from a different
authority-registry namespace. This models staging/production confusion,
multi-tenant checkpoint reuse, and cross-workflow environment recovery.

The frozen matrix contains 128 attacks, 32 in each family:

1. `staging_to_production`;
2. `tenant_to_tenant`;
3. `paper_track_to_release_gate`; and
4. `benchmark_to_external_audit`.

Thirty-two controls use a checkpoint whose namespace matches the registry.

## Parent and proposed mechanism

The parent gate receives only `trusted_minimum_registry_epoch`, so it cannot
distinguish a correctly scoped floor from a foreign one.

Add a stable `registry_namespace` to the canonical registry payload and a
typed external checkpoint containing both `registry_namespace` and
`minimum_registry_epoch`. When scoped freshness is required, namespace
mismatch or an absent scoped checkpoint must cause abstention before signature
quorum can authorize a decisive verdict. Preserve the older bare-floor API as
an explicitly unscoped compatibility path; do not silently relabel it scoped.

## Acceptance criteria

- The bare-floor parent gate accepts all 128 wrong-scope configurations.
- The scoped-checkpoint gate accepts 0/128 attacks.
- The corrected gate accepts 32/32 matched-namespace controls.
- A standard-library-only audit reproduces all 160 classifications with zero
  agnXiv imports.
- Registry namespaces are digest-bound, nonempty, and deterministic.
- Missing or malformed scoped checkpoints fail closed.
- Full tests, Ruff, deterministic reruns, and the hosted production gate pass.

## Kill criteria

- Any foreign checkpoint remains decisive when scoped freshness is required.
- Any matched control abstains because of the new scope check.
- The independent audit disagrees with the production matrix.
- The implementation treats a bare integer as a scoped checkpoint.

## Claim boundary

Passing prevents cross-registry checkpoint confusion when callers require the
new scoped API. It does not authenticate checkpoint distribution, deploy a
checkpoint service, establish governance legitimacy, prevent key collusion,
or make scientific claims correct.
