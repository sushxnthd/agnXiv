# Central-claim production validation protocol v1

Frozen before the final disjoint external validation run on 2026-10-19.

## Product target

AgnXiv centrality is a discovery/routing mechanism, not verifier evidence. The
zero-manifest path can freeze and execute up to four claim locators from a
single research run. Production safety therefore depends on placing a central
quantitative statement inside the verification slate, not on forcing exactly
one number to rank first.

## External source

Use ReproRepo paper metadata pinned to commit
`470a4c69d9f11df15526464e0a5bb66d95a12f55`.

All paper clusters inspected during development are frozen in
`research/benchmarks/centrality-dev-paper-clusters-v1.txt` and must be
excluded from the release evaluation.

## Gold construction

For each remaining paper with a public repository and at least two
quantitative abstract candidates:

1. Prefer a unique quantitative author/OpenReview TLDR-to-abstract match.
2. Otherwise map author title + optional TLDR to one abstract quantitative
   statement using a frozen lexical F1 anchor.
3. The fallback requires at least two shared content tokens, F1 >= 0.08, and
   a margin >= 0.015 over the runner-up.
4. Reject cases without a unique external map rather than guessing.

This gold construction never consults AgnXiv's centrality score.

## Release thresholds

The release set must contain at least 75 disjoint papers across at least three
conference/year strata.

- Recall@3 >= 0.90.
- Recall@5 >= 0.95.
- Recall@1 is reported as a diagnostic and is not a release gate.

The thresholds are evaluated once on the next untouched eligible set after
freezing this protocol. A failed set becomes development data; it must not be
reused as held-out evidence after tuning.

## Scope

Passing this gate establishes abstract-level quantitative central-claim
routing under external author metadata. It does not establish semantic
centrality for every claim in a full paper, and it cannot affect numeric
verification verdicts.
