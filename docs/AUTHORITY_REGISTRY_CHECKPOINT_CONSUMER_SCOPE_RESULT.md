# Consumer-scoped checkpoint-history commitment

## Result

The recursive checkpoint-history commitment authenticated the exact signed
authority-policy path but not the identity of the workflow consuming it.  When
two consumers deliberately shared a registry namespace, the parent gate
accepted **128/128** replays of a valid history commitment across repository,
workflow, or deployment-environment boundaries.

The new typed consumer-scope envelope reduced this to **0/128 false passes**.
All **32/32** matched-scope controls remained definitive.  Four preregistered
replay families were blocked in **32/32** cases each:

- staging workflow to production workflow;
- tenant A repository to tenant B repository;
- paper-review workflow to release workflow;
- benchmark environment to external-audit environment.

## Mechanism

`RegistryCheckpointConsumerScope` canonically identifies the trusted local
repository, immutable workflow reference, and deployment environment.
`registry_checkpoint_scoped_history_commitment_sha256` hashes that typed scope
together with the already-verified recursive history commitment.

Consumer-scoped mode is opt-in and requires recursive history-commitment mode.
It fails closed for a missing scope or envelope, malformed envelope,
incomplete mode configuration, or a mismatched repository, workflow, or
environment.  The production gate executes both the attack matrix and the
independent audit.

## Independent audit

The zero-production-import checker reconstructed and verified:

- **960** Ed25519 checkpoint signatures;
- **480** authority-registry digests;
- **320** recursive statement links;
- **160** final history commitments;
- **320** consumer-scope payloads;
- exactly **32** matched envelopes, all controls.

It independently confirmed 128/128 parent false passes, 0/128 scoped false
passes, and 32/32 preserved controls.

## Product consequence

A protected workflow can now provision one digest that means not only “this
exact authority history” but “this exact authority history for this repository,
workflow, and environment.”  A valid staging or tenant commitment therefore
cannot silently authorize production or another tenant merely because both use
the same registry namespace.

## Limitations

The guarantee depends on correct local scope and envelope provisioning.  It
does not secure the provisioner or configuration store, prove repository or
workflow legitimacy, discover unseen checkpoints, establish global canonicity,
or replace transparency logs.  No live deployment or independent reviewer-key
operation is claimed.
