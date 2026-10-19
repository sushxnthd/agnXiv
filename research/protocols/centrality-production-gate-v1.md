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


## Frozen external-source extension

The ReproRepo metadata source was exhausted after development exclusions: the
remaining unseen eligible slice contained 22 papers, which achieved Recall@3
= 1.00 and Recall@5 = 1.00 but cannot satisfy the frozen minimum sample size.

Before evaluating another source, the release protocol is therefore extended
to an untouched deterministic partition of SciTLDR-AIC. This is not model
training: AgnXiv has no learned centrality parameters and has never used the
selected rows for development.

The production SciTLDR holdout is frozen as:

- repository: `allenai/scitldr`
- commit: `5ccad9c00a60ad75c9e04abf7f27d0f53f983b20`
- file: `SciTLDR-Data/SciTLDR-AIC/train.jsonl`
- hash seed: `agnxiv-centrality-production-v1`
- partition: `uint64(sha256(seed + "|" + paper_id)[:8]) mod 4 == 0`
- gold: quantitative claims located directly inside SciTLDR oracle sentences;
  qualitative-only oracle cases are excluded
- nearest-sentence fallback: disabled

The same frozen release thresholds apply unchanged: at least 75 eligible
papers, Recall@3 >= 0.90, and Recall@5 >= 0.95. Recall@1 remains diagnostic.
If this partition fails, bucket 0 becomes development evidence and cannot be
reused for certification after any tuning.


## Frozen dense author-TLDR holdout

The direct-oracle SciTLDR bucket 0 was intentionally conservative but yielded
only two eligible quantitative oracle-sentence cases from 510 rows. It is now
development evidence and is not reused.

Before evaluating another partition, the dense author-TLDR mapping is frozen
on hash bucket 1 of the same untouched upstream corpus:

- hash seed: `agnxiv-centrality-production-v1`
- partition: `uint64(sha256(seed + "|" + paper_id)[:8]) mod 4 == 1`
- external anchor: `target[0]`, documented by SciTLDR as the author TLDR
- first preference: a unique quantitative author-TLDR value maps to a unique
  source quantitative claim with compatible metric/unit semantics
- fallback: title + author-TLDR lexical F1, requiring >=2 shared content
  tokens, F1 >=0.08, and a >=0.015 margin over the runner-up
- ambiguous mappings are excluded rather than guessed

The centrality score is never consulted while constructing gold. The frozen
release thresholds remain unchanged: n >= 75, Recall@3 >= 0.90, Recall@5 >=
0.95, with Recall@1 diagnostic only. If bucket 1 fails, it becomes development
evidence and cannot be reused after tuning.
