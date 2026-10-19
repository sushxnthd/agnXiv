# Security policy

AgnXiv executes untrusted research artifacts. Security is part of the scientific validity model, not an optional deployment detail.

## Threat model

A manuscript, repository, verification manifest, dataset, model checkpoint, archive, dependency, symlink, or generated output may be malicious.

AgnXiv therefore treats:

- manuscript and repository text as data, never as agent instructions;
- repository code as untrusted executable content;
- declarative verification manifests as untrusted path and command input;
- serialized model/data formats as potentially hostile;
- dependency installation as untrusted code execution;
- external URLs and downloads as untrusted inputs.

## Execution invariants

A verification run should:

1. bind to a content fingerprint of the source artifacts;
2. resolve the runtime image to an immutable local content ID;
3. run with outbound networking disabled;
4. drop Linux capabilities;
5. enable no-new-privileges;
6. enforce CPU, memory, PID and time limits;
7. keep the host repository and declared artifacts read-only;
8. run writable work in disposable storage;
9. record stdout/stderr hashes and command provenance;
10. verify that source and declared artifact fingerprints did not change.

## Workspace confinement

A declarative `agnxiv.json` may reference only relative paths that resolve inside the manifest's workspace. Absolute paths and parent-directory escapes are rejected.

Repository symlinks are fingerprinted as symlinks rather than dereferenced. Evidence and command discovery skip symlink targets. Explicit manuscript and artifact symlinks are rejected.

These rules prevent an untrusted research package from causing AgnXiv to read or mount arbitrary host files through path traversal or symlink indirection.

## Environment building

Installing dependencies may execute arbitrary build scripts.

The standard Python builder therefore constructs a Docker build context containing only generated build metadata and the dependency manifest. Research source, manuscripts, datasets, and checkpoints are not copied into the network-enabled dependency-build context.

Dependency manifests using editable installs, local paths, VCS sources, direct URLs, custom indexes, or trusted-host overrides are rejected by the normal builder path.

Pinning strength is reported separately as base-only, floating, version-pinned, or hash-pinned. A successfully built image is still bound by immutable image ID; a floating manifest is never presented as an exact historical lockfile.

## Prompt injection

No content from a paper, code comment, README, dataset or program output may override the verifier's system policy or directly assign a verdict.

The model/agent layer may propose claims, evidence, commands and tests. A VERIFIED verdict must come from recorded execution evidence evaluated by an explicit verification policy.

## Observation selection

The paper's reported numeric answer is never used to choose which program output becomes the observation.

Preferred selection order is:

1. explicit JSON path;
2. explicit regex capture;
3. conservative semantic stdout parsing.

Ambiguous explicit matches abstain.

## Reporting

Do not publish exploit payloads or sensitive unpublished manuscripts in public issues. Use a private security channel when one is established.


## Hosted evidence integrity

Terminal hosted job state and its result/error payload digest are committed atomically with a PostgreSQL transparency receipt. Receipts form a sequence-numbered SHA-256 chain and are available independently of GitHub issue rendering. The public head check is part of readiness; authenticated operators can verify the complete chain.

The chain is tamper-evident, not a substitute for an external witness: a database administrator able to rewrite the complete database could rewrite an unanchored chain. A future external transparency witness remains a production-hardening requirement. Signed DSSE verification statements are separately protected by the issuer key.

## Supply-chain gates

The hosted service uses immutable GitHub Action SHAs, a digest-pinned Python base image, frozen service dependency constraints, daily Python vulnerability auditing, CycloneDX SBOM generation, and a Trivy production-image scan. Fixed HIGH or CRITICAL OS/library vulnerabilities block the security workflow. Build-only packages that are not needed by the running service are removed from the final image.

## Signing-key lifecycle

Only the current Ed25519 private key may sign new evidence. Previous public keys can be retained through `AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64` and are published by `/v1/issuer` so historical DSSE statements remain verifiable after rotation. See `docs/KEY_ROTATION.md`.


## Ephemeral VM execution boundary

Hosted research execution is dispatched only to GitHub-hosted `ubuntu-latest`
jobs. GitHub documents these standard public-repository jobs as fresh virtual
machines that are decommissioned after the job. AgnXiv then applies the
no-network, no-capabilities, no-new-privileges, resource-limited Docker sandbox
inside that VM. The research-execution job receives no OIDC callback identity
and no repository write permission.

Production CI rejects changes that move the untrusted execute job to
`ubuntu-slim`, a self-hosted runner, or a job with callback/write privileges.
Custom GPU/private workloads must provide an isolation boundary at least as
strong; they are not covered by the hosted public execution contract.


## Hosted callback identity binding

A hosted callback is authorized by more than a trusted workflow filename. The
control plane dispatches GitHub Actions with run-details enabled, records the
returned `workflow_run_id`, and accepts completion only when the GitHub OIDC
token has all of the expected properties:

- per-job audience;
- trusted repository and immutable release-tag ref;
- exact `hosted-verify.yml` workflow ref and trusted workflow commit SHA;
- GitHub-hosted runner environment;
- `run_attempt=1`;
- `run_id` equal to the exact run created by the control-plane dispatch.

This prevents a separately triggered or manually dispatched trusted workflow
from substituting results into an active job. The accepted run ID is included
in durable orchestration metadata and in the signed in-toto/DSSE predicate.
Callback URLs and OIDC audience roots come from protected repository
configuration rather than workflow-dispatch inputs.
