# Recursive checkpoint-history commitment

## Result

Root-and-tip pinning did not authenticate the path between those endpoints.
The trusted tip digest covered namespace, epoch, and final registry snapshot,
but omitted `previous_statement_sha256`. An alternate fully signed intermediate
history could therefore preserve both trusted endpoint pins.

The frozen attack matrix produced **128/128 false passes** across revocation,
trust-domain, authority-quorum, and key-set substitutions. Every attack used
valid Ed25519 quorums and the same root and final authority-registry snapshots.

The new opt-in recursive commitment mode reduced this to **0/128 false passes**.
All **32/32** honest controls remained definitive, and each attack family was
blocked in **32/32** cases.

## Mechanism

`registry_checkpoint_linked_statement_sha256` hashes the signer-independent
statement tuple:

```text
(namespace, epoch, registry snapshot digest, predecessor commitment)
```

Each successor must name the full linked digest of its adjacent predecessor.
The workflow-provisioned final commitment therefore transitively binds every
retained checkpoint back to the root. Changing any intermediate registry or
link changes the final commitment even when the old root and tip statement
pins remain unchanged.

The mode fails closed unless transitive-chain, trusted-root, and trusted-tip
validation are all enabled. Missing, malformed, wrong-path, stale, or
misconfigured commitments also abstain.

## Independent audit

A zero-production-import verifier independently checked:

- **2,880 Ed25519 signatures**;
- **640 authority-registry digests**;
- **320 legacy statement links**;
- **640 recursive statement links**;
- **160 trusted-root pins**;
- **160 trusted-tip pins**;
- **320 final path commitments**.

It reconstructed both honest and substituted paths and confirmed that they
share the legacy endpoint pins but have different recursive commitments.

## Product consequence

Hosted workflows can now provision one final digest that commits to the exact
disclosed authority-policy history, rather than trusting two endpoints plus an
arbitrary signed path between them. The production gate runs both the attack
matrix and the independent audit.

## Limitations

This guarantees consistency only with the path and final commitment supplied
to the gate. It cannot discover an unseen later checkpoint, establish a
globally canonical history, secure the trusted commitment store, or substitute
for gossip and a public append-only transparency log. Production deployment
of independent reviewer keys and protected commitment distribution remains an
external launch requirement.
