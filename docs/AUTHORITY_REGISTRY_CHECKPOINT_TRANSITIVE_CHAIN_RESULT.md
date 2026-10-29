# Transitive checkpoint-history validation

## Result

The latest-link checkpoint gate accepted all 128 frozen attacks in which the
latest retained quorum and current quorum were linked correctly while an older
retained prefix was detached.  The verdict therefore depended on an
unvalidated historical prefix even though every individual checkpoint was
authentic.

The new optional transitive-chain gate validates every adjacent qualifying
quorum from the oldest supplied trust anchor through the current quorum.

- parent latest-link false passes: **128/128**;
- transitive-chain false passes: **0/128**;
- reversed-order false passes: **0/128**;
- fully linked three-epoch controls: **32/32**;
- revocation, trust-domain, authority-quorum, and key-set forks blocked:
  **32/32 each**;
- missing, malformed, mixed, skipped, and unknown/backward historical links
  all fail closed.

An independent script imports zero agnXiv modules.  It verified 960 Ed25519
signatures, reconstructed 480 registry digests and 320 statement links, and
reproduced the attack/control verdict counts.  The compressed raw evidence,
summary, and audit outputs reproduce byte-for-byte.

The full local regression is **273/273** tests, and scoped Ruff plus diff
integrity checks pass.

## Product consequence

Callers that retain more than one historical quorum can set
`require_registry_checkpoint_transitive_chain=True`.  This also enforces the
existing latest-to-current chain checks and suppresses a decisive scientific
verdict when any retained adjacent transition is not cryptographically linked.
The production gate executes and archives both the attack matrix and the
zero-import audit.

## Reproduce

```bash
PYTHONPATH=src:research/scripts python \
  research/scripts/verify_authority_registry_checkpoint_transitive_chain.py
python research/scripts/audit_authority_registry_checkpoint_transitive_chain.py
```

## Claim boundary

The guarantee is internal continuity for the authenticated history supplied to
the gate, rooted at its oldest supplied statement.  It does not prove that the
root is globally canonical, detect omitted history before the root or unseen
views, prevent deletion, provide cross-client gossip or transparency-log
inclusion, establish honest governance or secure key custody, guarantee
availability, or claim a deployed checkpoint service.
