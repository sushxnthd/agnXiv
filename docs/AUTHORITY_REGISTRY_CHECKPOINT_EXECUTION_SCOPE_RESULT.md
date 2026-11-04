# Execution-scoped checkpoint commitments block same-consumer replay

## Result

The consumer-scoped recursive-history gate is vulnerable to replay between
different executions of the same repository, workflow, and environment.  It
issued definitive scientific verdicts for **128/128** attacks because every
static consumer field and every signed history object remained authentic.

Binding the trusted consumer commitment to a typed execution identity reduced
those false passes to **0/128** while preserving **32/32** matched controls.

| Replay family | Parent false passes | Execution-scoped false passes |
|---|---:|---:|
| Earlier run to later run | 32/32 | 0/32 |
| Initial attempt to retry | 32/32 | 0/32 |
| Job to different job | 32/32 | 0/32 |
| Matrix shard to different shard | 32/32 | 0/32 |

## Mechanism

`RegistryCheckpointExecutionScope` canonically binds `workflow_run_id`,
positive `workflow_run_attempt`, and `workflow_job_id`.
`registry_checkpoint_execution_scoped_history_commitment_sha256` hashes that
identity with the already trusted consumer-scoped history commitment.

The mode is opt-in and depends on consumer-scope mode, which in turn depends on
recursive root-and-tip history commitment.  Missing, malformed, wrong-run,
wrong-attempt, wrong-job, and prerequisite-incomplete configurations all fail
closed.  The production verdict gate and hosted production workflow execute
the new checks.

## Independent audit

The independent verifier imports zero agnXiv modules and reconstructed:

- **960** Ed25519 checkpoint signatures;
- **480** authority-registry digests;
- **320** recursive history links;
- **160** final history commitments;
- **160** consumer-scope payloads;
- **320** execution-scope payloads;
- exactly **32** matching execution envelopes, all controls.

It independently recovered the parent's 128 false passes, the corrected gate's
zero false passes, and all 32 corrected controls.

## Product consequence

A hosted verifier can now require a checkpoint-history authorization minted for
the exact workflow execution rather than accepting any authorization valid for
the same long-lived deployment context.  This prevents a stale but authentic
authorization from crossing run, retry, job, or matrix-shard boundaries.

## Scope and limitations

This guarantee is only as trustworthy as provisioning and protection of the
execution identity and commitment.  It does not prove that CI metadata is
truthful, protect the provisioner or secret store, discover unknown newer
checkpoints, establish globally canonical history, or replace transparency
logs.  No live deployment or independent reviewer-key operation is claimed.
