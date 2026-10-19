# Central-claim regression v1 — 2026-10-19

**Evaluation role:** diagnostic_nonblind  
**Cases:** 3 frozen SciCoQA centrality annotations  
**Purpose:** regression detection only; not a held-out estimate of production accuracy.

## Result

The production claim-selection path was rerun from fresh real-paper diagnostic plans after correcting quantitative-extraction and centrality-scoring failures.

| Metric | Frozen v0 | v1 regression |
| --- | ---: | ---: |
| Recall@1 | 1/3 (33.3%) | 3/3 (100%) |
| Recall@3 | 2/3 (66.7%) | 3/3 (100%) |
| Recall@5 | 3/3 (100%) | 3/3 (100%) |
| Mean reciprocal rank | — | 1.000 |
| Mean NDCG@5 | — | 1.000 |

All three annotated central claims ranked first in the regenerated plans.

## Failures corrected

1. Hyphenated model/configuration identifiers such as model-name numeric suffixes were being interpreted as quantitative observations.
2. PDF-extracted image dimensions could be mistaken for scientific result values.
3. Multi-number citation lists could leak into quantitative claim candidates.
4. Early primary contribution statements were underweighted relative to later incidental metrics with explicit metric names.

The parser now rejects those false-claim families, and the centrality score includes a bounded early-paper contribution prior. This score is used only for discovery/ranking and cannot affect verifier evidence or verdict computation.

## Release interpretation

This result closes a regression failure, not the production gate. The three cases are known and non-blind. AgnXiv must still validate central-claim selection on a substantially larger held-out annotation set before claiming production-level centrality accuracy.

**CI evidence:** research-diagnostic run 39209951242.
