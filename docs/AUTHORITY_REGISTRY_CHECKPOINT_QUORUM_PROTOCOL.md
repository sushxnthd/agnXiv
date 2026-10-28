# Frozen protocol: checkpoint-authority quorum

Date frozen: 2026-10-28

## Threat model

The authenticated checkpoint gate proves that a checkpoint was signed by one
configured key, but one compromised checkpoint signer can still issue a valid
same-namespace low-floor checkpoint and revive a cryptographically valid
obsolete authority registry.

## Frozen attack

Construct 128 obsolete-registry cases across revocation, trust-domain, quorum,
and key-set rollback families.  Each case supplies a low-floor checkpoint
signed by one genuinely configured but compromised checkpoint key.  Measure
the existing single-signature authenticated gate before adding quorum logic.

Construct 32 current-registry controls signed by two independent checkpoint
authorities.

## Proposed mechanism

Add an explicit checkpoint quorum policy.  A checkpoint statement is usable
only when:

1. at least two distinct active checkpoint keys sign the same registry
   namespace and minimum epoch;
2. those keys span at least two configured checkpoint trust domains;
3. duplicate identities cannot count twice;
4. revoked, unknown, malformed, or invalid signatures do not count;
5. no raw or legacy checkpoint silently satisfies quorum mode.

The checkpoint trust root remains external to the authority registry being
protected.

## Adversarial controls

The verifier must separately reject:

- repeated copies of one valid signature;
- two keys controlled by one trust domain;
- valid signatures over disagreeing namespace or epoch statements;
- a quorum containing a revoked checkpoint key;
- a valid obsolete-floor signature combined with an honest current-floor
  signature.

The last case must not lower the effective floor.  A qualifying current-floor
quorum is required.

## Acceptance

- Parent single-signer false passes: 128/128.
- Quorum-gated false passes: 0/128.
- Current-registry controls retained: 32/32.
- Every adversarial control fails closed.
- Independent standard-library audit reproduces the matrix with zero agnXiv
  imports.
- Evidence is deterministic.
- Full tests, Ruff, and diff checks pass.

Any threshold bypass is a falsification and must be preserved.  A threshold
that rejects valid two-domain controls is also a failure.

## Claim boundary

Passing establishes resistance to one compromised checkpoint trust domain
under a configured two-domain threshold.  It does not prove independence of
the real organizations behind those domains, secure key installation,
Byzantine safety above the configured threshold, checkpoint availability, or
a deployed checkpoint distributor.
