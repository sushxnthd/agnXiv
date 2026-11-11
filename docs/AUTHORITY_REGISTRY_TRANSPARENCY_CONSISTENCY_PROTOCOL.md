# Frozen protocol: transparency append-only consistency gate

UTC date: 2026-11-11

## Launch-critical question

The current strict gate authenticates a fresh transparency root and verifies
inclusion against it, but it does not prove that the fresh tree extends a
previously authenticated tree. A log operator can sign a fresh replacement
history and still pass all existing checks.

## Frozen attack matrix

Construct an authenticated eight-leaf prior checkpoint and a fresh sixteen-leaf
current checkpoint. The provenance statement remains included in the current
tree. Evaluate 32 deterministic cases in each family:

1. missing prior authenticated checkpoint;
2. non-advancing or truncated tree size;
3. rewritten historical prefix under a newly signed fresh root;
4. tampered consistency audit path.

Also evaluate 32 valid append-only controls.

## Predictions

- The current signed-fresh-checkpoint gate accepts all 128 attacks because each
  current root is validly signed, fresh, and inclusion-valid in isolation.
- A corrected gate requiring an authenticated prior checkpoint and an RFC
  6962-style consistency proof accepts 0/128 attacks and 32/32 controls.
- Missing configuration, endpoint mismatch, invalid size ordering, invalid
  prior/current signatures, and inconsistent timestamps fail closed.
- A zero-production-import audit independently recomputes both roots, both
  signatures, every consistency path, and all 160 decisions.

## Implementation boundary

Strict mode will bind the consistency witness to the exact prior and current
signed checkpoints under the configured log key. It will require the same log
ID, a strict tree-size advance, an earlier prior issuance time, and a valid
append-only proof.

## Claim boundary

A pass proves append-only extension between two authenticated checkpoints for
one configured log key. It does not prove global canonicity, cross-client
gossip, secure key custody, absence of split views, actual producer execution,
or live deployment.
