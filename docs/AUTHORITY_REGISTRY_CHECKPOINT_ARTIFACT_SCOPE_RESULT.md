# Artifact-scoped checkpoint commitments

## Result

Execution-scoped authority-history commitments accepted **128/128** replays
where the repository, workflow, environment, run, attempt, and job were
unchanged but the scientific artifact was substituted.

The new artifact-scoped commitment produced:

| Attack family | Execution-scoped false passes | Artifact-scoped false passes |
|---|---:|---:|
| Manuscript substitution | 32/32 | 0/32 |
| Repository-tree substitution | 32/32 | 0/32 |
| Claim-manifest substitution | 32/32 | 0/32 |
| Evidence-bundle substitution | 32/32 | 0/32 |
| **Total** | **128/128** | **0/128** |

All **32/32** matched controls remained definitive.  Missing or malformed
artifact commitments, missing scopes, incomplete execution configuration, and
each individually mismatched digest fail closed.

## Mechanism

`RegistryCheckpointArtifactScope` contains canonical lowercase SHA-256 digests
for the manuscript, repository tree, claim manifest, and evidence bundle.  The
artifact commitment hashes the complete typed scope together with the trusted
execution-scoped commitment.  The gate requires the entire preceding chain:
authenticated recursive history, root and tip pins, history commitment,
consumer scope, execution scope, and finally artifact scope.

The implementation is integrated through both hosted-verdict entry points and
the production-gate workflow.  The new commitment is therefore an executable
abstention boundary rather than a report-only detector.

## Independent audit

The zero-production-import verifier reconstructed and checked:

- 960 Ed25519 checkpoint signatures;
- 480 authority-registry digests;
- 320 recursive statement links;
- 160 history commitments;
- 160 consumer-scope payloads;
- 160 execution-scope payloads;
- 320 artifact-scope payloads; and
- 32 matched artifact envelopes.

The primary and independent artifacts are deterministic gzip/JSON evidence and
are regenerated in hosted production-gate validation.

## Limits

This mechanism assumes the four trusted digests are correctly generated and
provisioned outside the untrusted artifact.  It does not secure CI metadata or
the secret store, prove sandbox containment, discover unknown authority
checkpoints, establish global canonicity, or constitute evidence of a live
hosted deployment.  It binds one configured execution to one configured
scientific object and fails closed on mismatch.