# Blind Paper-Code Discrepancy Pilot

This pilot uses four public SciCoQA real discrepancies only for post-hoc evaluation.

## Separation rule

The detector receives only:

- exact paper version;
- exact GitHub repository;
- exact commit.

It must not receive the linked GitHub issue, discrepancy description, category, author response, or SciCoQA explanation before producing its candidate discrepancy report.

The gold file `discrepancy-gold-v0.jsonl` is loaded only after detection.

## Initial taxonomy

- algorithm/state-update mismatch;
- implementation-scope or initialization mismatch with author clarification;
- objective/loss/masking mismatch;
- evaluation-protocol or leakage mismatch.

These categories are deliberately heterogeneous. The purpose of v0 is not to claim benchmark performance from four cases, but to force AgnXiv's alignment system to represent materially different kinds of paper-code disagreement.

## Required output for each blind run

1. paper proposition or procedure allegedly implemented;
2. exact paper passage location;
3. exact code path/symbol/lines;
4. mismatch type proposed by the detector;
5. confidence;
6. whether execution is needed to resolve the discrepancy;
7. no scientific verdict until deterministic evidence is available.

## Scoring

Report candidate recall@k and evidence-localization precision separately from scientific-verdict accuracy. A detector gets no credit for naming the right discrepancy category without locating both paper and code evidence.
