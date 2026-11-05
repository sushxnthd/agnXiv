# Authority checkpoint artifact-digest profile result

## Result

The artifact-scoped gate accepted all 128 attacks in which every committed
SHA-256 value remained unchanged but the derivation semantics of one digest
changed. A commitment to an artifact digest is therefore insufficient unless
the workflow also commits to what those bytes mean.

The new digest-profile-scoped gate produced:

- artifact-scoped false passes: **128/128**;
- digest-profile-scoped false passes: **0/128**;
- matched controls accepted: **32/32**;
- manuscript raw-bytes to normalized-text substitutions blocked: **32/32**;
- Git-tree to archive-bytes substitutions blocked: **32/32**;
- canonical-JSON to raw-JSON substitutions blocked: **32/32**;
- Merkle-manifest to archive-bytes substitutions blocked: **32/32**.

Missing, malformed, mismatched, and incompletely configured profile modes all
fail closed. Profile mode can only be enabled above artifact-scope mode.

## Mechanism

`RegistryCheckpointArtifactDigestProfile` provides a closed vocabulary for the
derivation procedure used by each scientific artifact digest. The new envelope
hashes the full typed profile together with the artifact-scoped history
commitment. A change in normalization, serialization, or bundle construction
therefore changes the trusted commitment even when the hexadecimal artifact
digest supplied to the workflow is unchanged.

## Independent audit

The zero-production-import auditor reconstructed 160 trusted profile
commitments and checked 320 source/effective payloads. Exactly the 32 matched
controls reproduced the trusted effective commitment; all 128 semantic
substitutions differed.

## Bounded claim

This closes replay across the four declared digest-derivation profiles. It does
not prove that an external producer actually followed the declared procedure,
protect the trusted commitment store, establish global artifact canonicity, or
constitute evidence of a live deployment. Those require independently executed
digest producers, transparency, and hosted-job evidence.

