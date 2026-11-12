# Frozen protocol: administrative-domain quorum for transparency gossip

## Launch-critical gap

The authenticated gossip gate requires distinct observer identities and keys,
but it does not currently require independent administrative control.  One
operator can register multiple observer IDs and keys, present mutually
consistent observations, and satisfy the two-observer gate without any
independent corroboration.

This protocol is frozen before changing the production model or opening the
attack outcomes.

## Candidate mechanism

Bind a canonical administrative-domain identifier into every signed gossip
observation and its trusted observer record.  Strict gossip authorization must
require both:

1. the configured minimum number of distinct authenticated observers; and
2. the configured minimum number of distinct authenticated administrative
   domains.

Domain identifiers are normalized by trimming surrounding whitespace and
case-folding.  The domain in a signed observation must equal the trusted
registry binding for that observer.  Missing legacy bindings collapse into one
non-independent domain and cannot satisfy a two-domain quorum.

## Prospectively frozen matrix

Use 32 deterministic seeds for each attack family and 32 valid controls:

1. `same_domain_two_identities`: two keys and IDs controlled by one domain;
2. `same_domain_three_identities`: three keys and IDs controlled by one domain;
3. `canonical_domain_alias`: spelling, case, and whitespace aliases of one
   domain presented as if independent; and
4. `signed_registry_domain_mismatch`: an observation signed for one domain is
   paired with a trusted-record reassignment to another domain.

All checkpoints and cross-view consistency proofs remain otherwise valid, so
the experiment isolates observer independence rather than log-history failure.

## Frozen predictions

| Gate | Attack false passes | Valid controls |
| --- | ---: | ---: |
| Existing distinct-identity gossip | 128/128 | 32/32 |
| Administrative-domain quorum | 0/128 | 32/32 |

Each attack family must be blocked 32/32.  Valid controls use two separately
bound domains and must remain definitive.

## Decision rule

The mechanism passes only if the complete frozen matrix matches the table,
the domain field is covered by the observer signature, canonical aliases
collapse deterministically, registry-domain mismatch fails closed, and an
independent zero-production-import audit reproduces every classification.
Any false pass or rejected valid control is preserved as a falsification.

## Production consequence and limits

Passing changes the verdict gate from identity-count quorum to an explicitly
configured identity-and-domain quorum.  It does not prove that the named
domains are truly independent, that keys have separate custody, or that any
observer is deployed.  Those remain external audit and launch gates.  Keep PR
#50 draft, conflicted, and unmerged.
