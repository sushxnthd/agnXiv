# Authority registry snapshot binding protocol

Status: frozen before implementation or attack execution.

## Question

Can an otherwise valid authority signature be reinterpreted under a different
trusted-authority registry snapshot because the signed authority scope does not
commit to registry policy?

The current scope binds the issuer, key identifier, scientific object, evidence
locator, and validity window. The verifier separately supplies the registry
that determines public keys, key status, trust-domain membership, and quorum
thresholds. This leaves a testable configuration-replay boundary: signatures
created under one registry may remain cryptographically valid after those
policy facts change.

## Frozen attack matrix

Use deterministic Ed25519 keys and 32 distinct scientific objects per family.
Every object receives two valid signatures created while the signing registry
places both keys in one trust domain and requires two signatures from two
domains. Evaluate the unchanged attestations under a substituted registry:

1. `trust_domain_remap`: relabel the two keys into distinct domains.
2. `revocation_rollback`: sign under a snapshot where the second key is
   revoked, then evaluate under an older snapshot where it is active.
3. `quorum_downgrade`: reduce the required signature/domain thresholds after
   signing so a one-domain set becomes decisive.
4. `key_policy_swap`: preserve issuer, key ID, and public key while changing
   the associated domain/status policy through a replacement snapshot.

The parent boundary is expected to accept all 128 substituted-registry cases
for which the replacement snapshot supplies a nominal quorum. This expectation
is a falsifiable pre-registration, not a result.

## Correction under test

Define a canonical SHA-256 digest of the complete registry model, including its
schema version, quorum thresholds, ordered key records, public keys, trust
domains, and status values. Add that digest to the signed authority scope.
Verification must require the signed digest to equal the exact registry used to
interpret the attestation.

The corrected boundary must reject all 128 substituted-registry cases and
accept 32 controls whose signatures bind the exact verification registry.

## Independent check

A standard-library-only audit must independently:

- canonicalize every registry snapshot and recompute its SHA-256 digest;
- compare signed and verification-registry digests;
- replay all 128 attacks and 32 controls from the raw JSON evidence;
- import no `agnxiv` modules.

## Pass and abstention criteria

Pass only if the parent accepts 128/128 attacks, the corrected gate accepts
0/128 attacks and 32/32 controls, the independent audit reproduces every case,
the result is deterministic byte-for-byte, the full test suite passes, and
removing or changing the registry digest causes conservative abstention.

If fewer than 128 parent cases accept, preserve the negative result, explain
which existing invariant already blocks them, amend the matrix before opening
new evidence, and do not retrofit the frozen expectation.

## Bounded claim

Registry-digest binding prevents silent reinterpretation of signatures under a
different registry configuration. It does not prove registry freshness,
governance legitimacy, append-only publication, external reviewer independence,
or scientific correctness. A verifier can still deliberately select and trust
the wrong snapshot; that choice must be governed outside this mechanism.
