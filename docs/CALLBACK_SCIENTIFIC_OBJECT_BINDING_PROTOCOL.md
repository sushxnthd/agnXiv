# Frozen protocol: callback scientific-object binding

Status: frozen before implementation and before attack replay.

## Failure hypothesis

The hosted callback authenticates its GitHub Actions caller, checks the pinned
repository commit, and binds `auto_planned` authority to the submitted frozen
locator. It does not currently prove that the callback's manuscript identity
belongs to the requested arXiv job, that every bundle fingerprints that same
manuscript, or that a frozen locator names the claim carried by its bundle.

Consequently, a correctly structured result from another manuscript or claim
may be replayed into a job sharing the same repository commit. Recomputing the
authority-evidence digest does not repair this because it only proves internal
digest consistency, not scientific-object coherence.

## Preregistered attacks

For 128 deterministic cases, replay each of these mutations while keeping the
repository commit, authority label, locator digest, and verdict internally
valid:

1. substitute another arXiv identifier in `manuscript_identity`;
2. substitute another manuscript SHA-256 in the bundle;
3. substitute another manuscript SHA-256 in an additional verification;
4. substitute another claim identifier in the frozen locator and recompute its
   authority digest;
5. substitute another metric in the frozen locator and recompute its authority
   digest.

Positive controls retain one versioned arXiv identity, one manuscript digest,
and exact locator/bundle claim coherence.

## Required correction

At the service callback boundary, before accepting a scientific result:

- normalize and match the result arXiv identifier to the job arXiv identifier;
- require a canonical SHA-256 manuscript identity;
- require every primary and additional bundle to fingerprint that exact
  manuscript;
- require every frozen locator's claim identifier and metric to equal its
  bundle claim;
- preserve existing repository, authority, locator-digest, and status checks.

## Success and kill criteria

Success requires zero accepted cross-object attacks, all valid controls
accepted, unchanged provisional/decisive verdict semantics after validation,
an independent stdlib-only audit, and the complete repository test suite.
Any accepted mutation kills the claim. If the correction requires trusting an
unsigned client assertion, report failure rather than marking the launch gate
closed.

## Bounded interpretation

This establishes callback coherence among already authenticated job and worker
objects. It does not prove the paper is scientifically correct, pin an arXiv
document across time when the job itself lacks an expected digest, or replace
independent reviewer authority.
