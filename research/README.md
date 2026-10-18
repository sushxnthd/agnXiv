# AgnXiv Research Program

Started 2026-10-18. This directory turns product assumptions into falsifiable experiments.

## Research objective

Build an automated scientific verifier whose strongest claim is not that it completes many tasks, but that when it emits a positive scientific verdict the verdict is exceptionally reliable.

## Program rules

1. False passes are more costly than abstentions.
2. Output-locator discovery is blinded to the paper's reported numeric answer.
3. Public benchmark cases with known discrepancies are diagnostic, not headline blind evaluations.
4. Every benchmark case pins the paper version and code commit when available.
5. Models may propose claims, files, commands, lineage links, or tests; deterministic evidence decides numeric verdicts.
6. Process metrics are recorded at each stage rather than only scoring the final result.

## Active tracks

- `bench100` — stratified 100-paper evaluation with full failure taxonomy.
- `selective` — risk/coverage curves and abstention calibration.
- `scicoqa` — execution-grounded paper-code discrepancy detection.
- `env` — historical environment archaeology.
- `centrality` — central-claim ranking.
- `locator` — leakage-free observation discovery.
- `dag` — claim-evidence DAG extraction.
- `lineage` — cited-paper implementation lineage.
- `reimplementation` — V4 independent implementation.
- `aggregation` — independence-aware living evidence records.
- `redbench` — adversarial scientific-verifier attacks.
- `crossdomain` — physics, quantitative biology, and other computational sciences.

## First cohort

`benchmarks/scicoqa-pilot-v0.jsonl` contains eight real SciCoQA v1.1 cases with versioned papers and pinned repositories. These cases are explicitly marked `diagnostic_nonblind` because their discrepancies are public.

The existing DeepWalk and Perturbation-Based-Measurements runs remain external execution anchors. The next cohort will add held-out PaperBench/RECLAIM/AgentActionBench tasks under their native protocols rather than copying their labels into AgnXiv.

## Headline metrics

- false-pass rate
- false-divergence rate
- verification coverage
- selective error rate
- claim centrality recall@k
- blinded output-locator accuracy
- critical-path recall for claim-evidence DAGs
- historical environment recovery rate
- execution success rate
- human intervention rate
- wall-clock and compute cost
- evidence-independence sensitivity

## Publication tracks

**Paper A — Trustworthy Automated Scientific Verification**: selective verification, abstention, leakage-free observation selection, adversarial false-pass evaluation, and AgnXiv Bench.

**Paper B — Execution-Grounded Paper-Code Alignment**: compare static paper+code reasoning against claim-evidence graphs, environment analysis, and executable probes on SciCoQA-style discrepancies.

**Paper C — Living Evidence Records for Computational Science**: formalize Attempt → Record → Challenge → Response → Rerun and independence-aware aggregation of conflicting evidence.

## Status convention

`queued` means the protocol and case are registered but not yet executed; `running` means an experiment is actively executing in a reproducible workflow; `complete` requires committed outputs; `blocked` requires a documented blocker. No research result is claimed merely because a track is listed here.