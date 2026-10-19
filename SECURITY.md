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

## Outer worker boundary

The hosted path uses two isolation layers. Every research execution job runs on
a fresh GitHub-hosted VM, and the untrusted research process runs inside the
Docker sandbox described below. The execution job has no `id-token: write`
permission, receives no AgnXiv database/API/signing credentials, and does not
propagate host environment variables into the research container.

The callback is a separate job. It receives the short-lived OIDC capability
only after the execution job has completed and emitted a bounded result
artifact. `agnxiv.worker_boundary` fails closed when the hosted execution job
is not on a GitHub-hosted runner or when OIDC/service credentials are exposed.

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
