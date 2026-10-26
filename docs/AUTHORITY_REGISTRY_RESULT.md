# Trusted authority registry result

Protocol: `docs/AUTHORITY_REGISTRY_PROTOCOL.md` (committed before implementation and replay).

## Result

The predicted authorization flaw was reproduced. The prior gate issued a
definitive verdict for all 128 bundles whose only authority was a caller-set
`auto_planned` label plus a syntactically valid locator digest. Under the new
strict registry boundary, none did.

| Cohort | Definitive / total |
| --- | ---: |
| Prior gate, self-asserted authority | 128 / 128 |
| Strict gate, self-asserted authority | 0 / 128 |
| Strict gate, registered signed controls | 32 / 32 |
| Rogue-key attacks | 0 / 32 |
| Altered-locator attacks | 0 / 32 |
| Cross-claim replays | 0 / 32 |
| Cross-manuscript replays | 0 / 32 |
| Cross-repository replays | 0 / 32 |
| Expired-attestation replays | 0 / 32 |

An independent script that imports no agnXiv production modules replayed all
32 controls and all 192 attacks exactly. Raw primary and audit reports are in
`research/results/authority-registry.json` and
`research/results/authority-registry-audit.json`.

## Product consequence

The hosted `auto_verify` path now requests the strict registry boundary. No
external registry is configured in this repository, so this path deliberately
abstains instead of treating a self-asserted label as authority. This is a
safe launch gate, not evidence that a live registry or deployment exists.

## Bounded claim and remaining gates

The result establishes signature authentication, configured registry
membership, validity-window enforcement, threshold counting, and exact object
binding for this model and attack matrix. It does not establish reviewer
competence, institutional independence, scientific correctness, secure live
key custody, revocation operations, governance, or a deployed reviewer
registry. Those remain explicit production gates, together with external
security review and hosted integration evidence.
