# Frozen protocol: artifact-scoped checkpoint commitments

## Threat model

Execution scoping binds a verified authority-registry history to one repository,
workflow, environment, run, attempt, and job.  It does not bind the commitment
to the scientific object evaluated inside that job.  An attacker may therefore
reuse a valid execution-scoped commitment for another manuscript, repository
tree, claim manifest, or evidence bundle processed by the same execution.

This experiment tests 128 deterministic substitutions, 32 in each family:

1. manuscript digest substitution;
2. repository-tree digest substitution;
3. claim-manifest digest substitution;
4. evidence-bundle digest substitution.

All substituted artifacts remain syntactically valid.  The source authority
history, consumer identity, and execution identity remain authentic and
unchanged.  Thirty-two matched controls use the exact artifact scope for which
the commitment was provisioned.

## Frozen mechanism

Add a typed `RegistryCheckpointArtifactScope` containing four canonical
lowercase SHA-256 digests.  Compute an artifact-scoped commitment by hashing
the full typed scope together with the trusted execution-scoped commitment.
Artifact mode must require every preceding root, tip, history, consumer, and
execution mode.  Missing, malformed, mismatched, or incompletely configured
artifact scopes must fail closed.

## Success and falsification gates

- The execution-scoped parent gate must falsely pass all 128 substitutions.
- Artifact scoping must pass 0/128 substitutions and 32/32 controls.
- Every attack family must be blocked 32/32.
- A zero-production-import audit must reconstruct signatures, registry
  digests, recursive links, all nested commitment envelopes, and final verdict
  counts.
- Deterministic artifacts, focused tests, the full suite, lint, and diff
  integrity must pass before publication.

The result does not claim trusted digest generation, secure provisioning,
global registry canonicity, sandbox containment, or a verified live
deployment.  It isolates one replay boundary only.

