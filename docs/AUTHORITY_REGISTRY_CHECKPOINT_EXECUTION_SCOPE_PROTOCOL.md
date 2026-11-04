# Frozen protocol: checkpoint commitment execution scope

Status: frozen before implementation and attack execution.

## Threat model

The consumer-scoped history commitment binds repository, immutable workflow
reference, and deployment environment, but those fields are constant across
many workflow executions.  Test whether an authentic envelope provisioned for
one execution can be replayed within the same consumer across:

1. an earlier workflow run and a later workflow run;
2. an initial run attempt and a retry attempt;
3. one job and a different job in the same run;
4. one matrix shard and another shard in the same job family.

Construct 32 deterministic attacks per family, 128 total, plus 32 exact-scope
controls.  Every attack keeps the signed authority history and static consumer
scope valid.  The parent consumer-scoped gate is expected to issue a definitive
verdict; the corrected gate must abstain.

## Frozen mechanism

Introduce a typed trusted execution identity containing:

- `workflow_run_id`;
- positive `workflow_run_attempt`;
- `workflow_job_id`.

Hash that canonical identity together with the already trusted
consumer-scoped history commitment.  Execution-scoped mode is opt-in and must
fail closed unless recursive history commitment and consumer-scope modes are
also enabled.  Missing, malformed, mismatched, or incompletely configured
execution identities and envelopes must abstain.

The production verdict gate must expose the mode.  The hosted production gate
must execute the attack matrix and independent audit.

## Acceptance criteria

- parent consumer-scoped false passes: 128/128;
- execution-scoped false passes: 0/128;
- matched controls: 32/32;
- every attack family blocked: 32/32;
- negative configuration controls all fail closed;
- independent audit reconstructs signatures, registry digests, recursive
  links, history commitments, consumer envelopes, and execution envelopes with
  zero agnXiv imports;
- deterministic artifacts, Ruff, focused tests, and full regression pass.

## Claim boundary

Success proves replay resistance only relative to a correctly provisioned and
protected execution identity and trusted envelope.  It does not attest that CI
metadata is truthful, protect the provisioner or secret store, establish global
history, discover unseen checkpoints, or constitute a verified live deployment.
