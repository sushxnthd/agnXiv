# Authority checkpoint digest-producer result

## Result

The digest-profile-scoped gate accepted all 128 attacks in which the artifact
digests, artifact scope, digest profile, consumer, and execution remained
fixed while the declared digest producer changed.  The trusted derivation
profile alone therefore does not bind the implementation that produced the
values.

The new producer-scoped gate produced:

- digest-profile-scoped false passes: **128/128**;
- digest-producer-scoped false passes: **0/128**;
- matched controls accepted: **32/32**;
- producer identity substitutions blocked: **32/32**;
- implementation measurement substitutions blocked: **32/32**;
- runtime image substitutions blocked: **32/32**;
- toolchain manifest substitutions blocked: **32/32**.

Missing, malformed, mismatched, and incompletely layered producer modes all
fail closed.  Producer scope can only be required above digest-profile mode.

## Mechanism

`RegistryCheckpointDigestProducerScope` binds four independently inspectable
dimensions: producer identity, implementation SHA-256, immutable runtime image
digest, and toolchain-manifest SHA-256.  Its canonical payload is committed
above the digest-profile-scoped checkpoint history.  A producer substitution
therefore changes the expected commitment even when every scientific artifact
digest and declared derivation semantic remains identical.

This has a concrete gate consequence: a hosted scientific verdict abstains if
the effective producer scope does not reproduce the trusted producer-scoped
commitment.

## Independent audit

The zero-production-import auditor reconstructed all 160 trusted producer
commitments and checked 320 source/effective payloads.  Exactly the 32 matched
controls reproduced the trusted effective commitment; none of the 128
substitutions did.

## Bounded claim

This closes producer-metadata substitution across the four preregistered
dimensions.  It does **not** prove that the declared producer actually ran,
authenticate who measured its implementation, provide remote attestation or a
trusted execution environment, protect the trusted commitment store, or prove
a live deployment.  Those remain explicit production launch gates.

## Reproduction

```bash
PYTHONPATH=src:research/scripts python research/scripts/verify_authority_registry_checkpoint_digest_producer.py
PYTHONPATH=src python research/scripts/audit_authority_registry_checkpoint_digest_producer.py
```

The deterministic evidence is stored in
`research/results/authority-registry-checkpoint-digest-producer.json.gz` with
its summary and independent audit beside it.
