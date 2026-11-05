# Authority checkpoint artifact-digest profile protocol

## Status

Frozen before implementation and attack execution. This extends the existing
artifact-scoped checkpoint kernel; it does not start a second agnXiv kernel.

## Threat

The artifact-scoped commitment binds four SHA-256 values but not the procedure
used to derive those values. A valid commitment can therefore be replayed after
a workflow silently changes artifact semantics, for example from raw manuscript
bytes to normalized text, from a Git tree to archive bytes, from canonical JSON
to raw JSON, or from a Merkle manifest to an archive digest. The hexadecimal
values and every previously bound consumer/execution identity can remain fixed
while the scientific object represented by a digest changes.

## Frozen intervention

Add a typed `RegistryCheckpointArtifactDigestProfile` with four closed-vocabulary
derivation identifiers:

- manuscript: `raw-bytes-v1`;
- repository tree: `git-tree-v1`;
- claim manifest: `jcs-json-v1`;
- evidence bundle: `merkle-manifest-v1`.

Bind the complete profile above the artifact-scoped commitment. Profile mode
must require artifact mode and fail closed for missing, malformed, mismatched,
or partially configured profiles and commitments.

## Preregistered attack matrix

Create 32 deterministic cases for each semantic substitution:

1. manuscript `raw-bytes-v1` to `normalized-text-v1`;
2. repository `git-tree-v1` to `archive-bytes-v1`;
3. claims `jcs-json-v1` to `raw-json-v1`;
4. evidence `merkle-manifest-v1` to `archive-bytes-v1`.

The existing artifact-scoped gate is expected to accept all 128 substitutions.
The digest-profile gate must accept zero, while 32 matched controls pass.

## Required evidence

- production gate integration and unit validation for every profile dimension;
- deterministic 128-attack corpus plus 32 controls;
- zero-production-import audit of commitments and outcomes;
- full regression, lint, deterministic replay, and exact-head hosted evidence;
- explicit limitations: this binds declared derivation semantics but cannot
  prove that an external producer actually followed them.

