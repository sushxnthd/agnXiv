# External centrality validation v0 — 2026-10-19

**Evaluation role:** heldout_external_author_tldr  
**External source:** ReproRepo at `470a4c69d9f11df15526464e0a5bb66d95a12f55`  
**First-run CI:** scientific-validation run `39213010901`

## Frozen release thresholds

Before the first held-out evaluation, the production gate was fixed at:

- at least 75 distinct papers;
- Recall@1 >= 60%;
- Recall@3 >= 90%;
- Recall@5 >= 95%;
- at least three paper strata.

These thresholds are not reduced after observing results.

## First result

The strictest gold construction required an author/OpenReview TLDR to contain a quantitative claim whose value uniquely mapped to an abstract quantitative claim.

| Metric | Result |
| --- | ---: |
| Eligible papers | 16 |
| Recall@1 | 81.25% |
| Recall@3 | 93.75% |
| Recall@5 | 93.75% |
| Mean reciprocal rank | 0.8854 |
| Release gate | **FAIL** |

The result failed the predeclared gate because the sample was too small (16 < 75) and Recall@5 was below 95%. It is retained as evidence and is not converted into a passing result by lowering thresholds.

## Next protocol revision

The low yield is caused by the annotation rule: most author TLDRs summarize the primary contribution qualitatively rather than repeating a result number. The next evaluation therefore keeps the same papers, ranking function, and release thresholds but expands the *external gold mapping*:

1. exact quantitative TLDR-to-abstract mapping remains the strongest anchor;
2. otherwise, author TLDR/title content words are matched to quantitative abstract-claim sentences using a frozen lexical-overlap rule;
3. a paper enters the benchmark only when that mapping is unique and clears a predeclared score and margin;
4. AgnXiv's centrality score is never used to create the gold target.

This protocol change increases annotation yield without tuning the production ranking function to held-out outcomes.
