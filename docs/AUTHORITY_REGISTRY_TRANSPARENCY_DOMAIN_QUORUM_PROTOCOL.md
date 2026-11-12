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

Bind a canonical administrative-domain identifier to each observer in the
trusted observer registry.  Strict gossip authorization must require both:

1. the configured minimum number of distinct authenticated observers; and
2. the configured minimum number of distinct authenticated administrative
   domains.

Domain identifiers are normalized by trimming surrounding whitespace and
case-folding.  Missing legacy bindings cannot contribute to a domain quorum.
The binding is deliberately not self-asserted by the observer: an observer
signature authenticates the registered identity, while the independently
managed trusted registry supplies its administrative domain.

## Prospectively frozen matrix

Use 32 deterministic seeds for each attack family and 32 valid controls:

1. `same_domain_two_identities`: two keys and IDs controlled by one domain;
2. `same_domain_three_identities`: three keys and IDs controlled by one domain;
3. `canonical_domain_alias`: spelling, case, and whitespace aliases of one
   domain presented as if independent; and
4. `legacy_unscoped_observers`: distinct authenticated legacy observers have
   no administrative-domain binding.

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
the domain binding comes only from the trusted registry, canonical aliases
collapse deterministically, unscoped observers cannot satisfy quorum, and an
independent zero-production-import audit reproduces every classification.
Any false pass or rejected valid control is preserved as a falsification.

## Production consequence and limits

Passing changes the verdict gate from identity-count quorum to an explicitly
configured identity-and-domain quorum.  It does not prove that the trusted
registry is honest, that its named domains are truly independent, that keys
have separate custody, or that any observer is deployed.  Those remain
external governance, audit, and launch gates.  Keep PR #50 draft, conflicted,
and unmerged.
