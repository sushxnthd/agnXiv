# Frozen protocol: signed checkpoint-history linkage

Status: frozen before implementation and prospective attack execution.

## Threat

The current history-consistency gate authenticates supplied historical
checkpoints and detects same-epoch conflicts. It does not cryptographically
link a new checkpoint quorum to the latest retained historical statement.
Consequently, a server can present a valid quorum at a later epoch together
with an unrelated but internally valid history prefix. Because the epochs
differ, the current gate has no same-epoch conflict to detect.

## Predicted correction

Each checkpoint scope may carry `previous_statement_sha256`, the canonical
SHA-256 digest of the immediately preceding quorum statement
`(registry_namespace, minimum_registry_epoch, authority_registry_sha256)`.
The field is covered by the Ed25519 checkpoint signature.

When chain mode is required, the gate must:

- authenticate current and historical checkpoint quorums normally;
- select the unique latest qualifying historical statement in the current
  namespace;
- require every signer in the current qualifying quorum to endorse the same
  previous-statement digest;
- require that digest to equal the canonical digest of the latest historical
  statement;
- require the current epoch to be strictly later than the linked historical
  epoch;
- fail closed on absent, malformed, mixed, stale, or unknown links.

## Frozen attack matrix

- 128 detached-history attacks across revocation, trust-domain, authority-
  quorum, and key-set registry forks. The parent history gate is predicted to
  return a definitive verdict; chain mode must abstain.
- 32 correctly linked epoch-advance controls must remain definitive.
- Reversed checkpoint order must not alter any verdict.
- Missing history, missing links, malformed links, signer disagreement,
  same-epoch links, and links to a non-latest historical statement must fail
  closed.
- Independent verification must reconstruct every registry and statement
  digest, verify every Ed25519 signature, and import zero agnXiv modules.
- Raw, summary, and audit artifacts must reproduce byte-for-byte.

## Claim boundary

This can prove continuity only between signed quorum statements actually
retained by the trusted workflow. It cannot discover a view never observed by
any trusted party, make storage physically append-only, establish honest
governance or secure key custody, guarantee availability, or claim a deployed
transparency service.

Kill or reformulate if the parent gate does not false-pass the frozen attack,
if any chain-bound attack remains definitive, if any valid control abstains,
or if the independent audit disagrees.
