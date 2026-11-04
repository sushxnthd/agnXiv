# Frozen protocol: consumer-scoped checkpoint-history commitment

## Question

The recursive checkpoint-history commitment authenticates the exact disclosed
authority-policy path, but it contains only registry namespace, epoch, registry
snapshot, and predecessor commitment.  If two consumers intentionally share a
registry namespace, can a commitment provisioned for one repository, workflow,
or deployment environment be replayed to authorize the other?

## Frozen attack matrix

Construct 128 cross-consumer replay attacks, 32 in each family:

- staging workflow to production workflow;
- tenant A repository to tenant B repository;
- paper-review workflow to release workflow;
- benchmark environment to external-audit environment.

Every attack reuses an otherwise valid three-epoch recursively committed
history, valid Ed25519 checkpoint quorums, the same registry namespace and
snapshot, valid root and tip pins, and the correct unscoped final history
commitment.  Only the trusted consumer identity differs.

Construct 32 matched-scope controls.

The parent prediction is 128/128 false passes because consumer identity is not
an input to the current history commitment.

## Repair target

Add a typed consumer scope containing repository, immutable workflow reference,
and deployment environment.  Define a signer-independent envelope digest over
the recursive history commitment and the canonical consumer scope.  Trusted
workflows may require the supplied envelope to match both the already-verified
history commitment and their locally configured consumer scope.

The new mode must require recursive history-commitment mode and fail closed for
missing or malformed envelope digests, missing consumer scope, wrong
repository, wrong workflow reference, wrong environment, or incomplete mode
configuration.

## Success criteria

- Parent recursive-history false passes: 128/128.
- Consumer-scoped false passes: 0/128.
- Matched-scope controls definitive: 32/32.
- All four replay families blocked: 32/32 each.
- Independent zero-import audit verifies every signature, registry digest,
  recursive link, unscoped commitment, consumer-scope payload, and envelope.
- Deterministic artifacts reproduce byte-for-byte; full regression and Ruff
  pass.

## Stop conditions

Stop and preserve a negative result if the parent already distinguishes the
consumer scopes, if any matched control abstains, or if the repair requires
changing the signed authority history rather than binding trusted
distribution context.

## Scope

Passing would prevent accidental or adversarial cross-consumer reuse when a
trusted workflow provisions the correct local scope and envelope.  It would
not secure the provisioner, prove that a repository or environment is
legitimate, discover unseen checkpoints, establish global canonicity, or
replace protected secret/configuration distribution and transparency logs.
