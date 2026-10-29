# Signed checkpoint-history linkage

## Central result

The prior history-consistency gate authenticates retained checkpoints and
detects same-epoch equivocation, but it does not bind a later checkpoint
quorum to the latest retained statement. A valid later-epoch quorum can
therefore be paired with a detached but internally valid history prefix.

The new optional chain mode signs `previous_statement_sha256` inside each
checkpoint scope. The digest commits to the preceding quorum statement's
registry namespace, epoch, and canonical registry digest, independent of the
individual signers. A current quorum is accepted only when all its signers
agree on the link, the link matches the unique latest retained quorum, and the
epoch strictly advances.

## Adversarial result

| Gate | Detached-history false passes |
|---|---:|
| Authenticated history parent | 128/128 |
| Signed history chain | 0/128 |

The attacks span revocation, trust-domain, authority-quorum, and key-set
registry forks, with 32 prospective cases per family. Reversing current and
historical checkpoint order leaves all corrected verdicts unchanged.

## Controls and independent verification

- Correctly linked epoch advances: 32/32 definitive.
- Missing history: blocked.
- Missing or malformed link: blocked.
- Different links from the two quorum signers: blocked.
- Same-epoch link: blocked.
- Link to a valid but non-latest historical statement: blocked.
- Independent audit: 640/640 Ed25519 signatures verified.
- Independent audit: 320/320 registry digests reconstructed.
- Independent audit: 160/160 statement links reconstructed.
- agnXiv imports in independent audit: zero.

Raw, summary, and audit artifacts are deterministic and reproduced
byte-for-byte. The production workflow runs and archives both the attack
matrix and independent audit.

## Security boundary

The mechanism proves continuity only between signed quorum statements
actually retained and supplied by the trusted workflow. It does not discover
views never observed by a trusted party, make storage physically append-only,
provide cross-client gossip or transparency-log inclusion proofs, establish
honest governance or secure key custody, guarantee availability, or claim a
deployed checkpoint distributor.
