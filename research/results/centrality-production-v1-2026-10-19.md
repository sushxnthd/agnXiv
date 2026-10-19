# Central-claim production validation v1 — 2026-10-19

**Status:** PASS  
**Evaluation role:** heldout_external_multi_source  
**CI run:** 39224459349  
**Validated commit:** `e2de10c82d306ec469028107ee29aec477493361`

## Frozen production gate

AgnXiv centrality is a discovery/routing mechanism. It selects which quantitative
claims enter the verification slate; it does not contribute evidence to the
numeric verifier verdict.

The production gate was frozen at:

- at least 75 held-out papers;
- at least two disjoint external metadata sources;
- Recall@3 >= 0.90;
- Recall@5 >= 0.95;
- Recall@1 reported diagnostically, not used as a release threshold.

Development papers and previously evaluated hash partitions were excluded before
the production aggregate was run.

## External sources

### ReproRepo holdout

- Repository: `LithiumDA/ReproRepo`
- Pinned commit: `470a4c69d9f11df15526464e0a5bb66d95a12f55`
- Held-out papers: 22
- Recall@3: 1.0000
- Recall@5: 1.0000

Gold uses author/OpenReview TLDR quantitative mapping where available, with the
frozen title/TLDR lexical anchor as the fallback. All development paper clusters
are excluded.

### ICLR 2024 OpenReview holdout

- Repository: `astenuz/iclr2024-openreview`
- Pinned commit: `740c3112f479019d9902780fd627b0b7c19eac7c`
- Source: `data/iclr2024_papers.csv`
- Frozen hash seed: `agnxiv-openreview-centrality-v1`
- Production partitions: hash-modulus 5, buckets 1–4
- Previously observed bucket 0: excluded from certification
- Held-out papers: 64
- Recall@3: 0.984375
- Recall@5: 1.0000

Gold is derived from author title + author TLDR without consulting AgnXiv's
centrality score.

## Aggregate result

| Metric | Result | Gate |
| --- | ---: | ---: |
| External sources | 2 | >= 2 |
| Held-out papers | 86 | >= 75 |
| Recall@1 | 55.81% | diagnostic |
| Recall@3 | **98.84%** (85/86) | >= 90% |
| Recall@5 | **100%** (86/86) | >= 95% |
| Release result | **PASS** | PASS |

The complete aggregate was emitted as
`agnxiv.centrality-production-aggregate/1` by the immutable CI workflow and
uploaded with the two per-source reports.

## Interpretation boundary

This validates **abstract-level quantitative claim routing** against external
author metadata. It does not establish that AgnXiv can identify every
scientifically central statement in every full paper, and the centrality score
cannot set or change a verification verdict. Ambiguous discovery remains subject
to verifier abstention and explicit evidence requirements.
