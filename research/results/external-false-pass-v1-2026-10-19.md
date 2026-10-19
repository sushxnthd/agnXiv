# External false-pass validation v1 — 2026-10-19

**Evaluation role:** heldout_external_seeded_negative_control  
**External source:** ReproRepo, pinned at `470a4c69d9f11df15526464e0a5bb66d95a12f55`  
**CI run:** GitHub Actions `scientific-validation` run 39212606398

## Predeclared release criterion

The production false-pass gate requires:

- at least 299 distinct paper-level external clusters;
- zero false passes;
- a one-sided 95% exact zero-event upper bound no greater than 1%;
- at least three independent paper strata;
- at least eight adversarial output families.

The sample-size threshold is statistical rather than cosmetic: with zero observed false passes, 299 independent trials are the first integer sample size for which the exact one-sided 95% upper bound falls below 1%.

## Result

| Metric | Result |
| --- | ---: |
| Distinct external paper clusters | 308 |
| False passes | 0 |
| Unexpected verifier decisions | 0 |
| Adversarial families | 10 |
| One-sided 95% false-pass upper bound | 0.9679% |
| Production false-pass gate | **PASS** |

The 308 cases are deterministically sampled from pinned ReproRepo NeurIPS 2022, NeurIPS 2024, and ICLR 2026 paper lists. Each case is seeded by one distinct paper/repository pair and exactly one case is counted per paper cluster.

The ten frozen stress families cover reported-value echoes, reference/expected-value decoys, measured/evaluation cues, same-line target/observation ambiguity, validation-vs-test ambiguity, repeated metric ambiguity, and unrelated-metric decoys.

## Interpretation

This closes the **false-pass statistical safety** launch gate for the tested answer-leakage and locator-selection threat model. It does not establish that AgnXiv can execute 308 real repositories, recover their historical environments, or identify every paper's central claim.

Those remain separate production gates:

1. held-out central-claim selection;
2. historical environment recovery;
3. real-paper execution coverage.

The distinction is intentional: synthetic transformation families may stress a verifier failure mode, but they cannot substitute for execution or environment-recovery evidence.

## Reproducibility

The benchmark is implemented in:

- `research/scripts/run_external_false_pass_validation.py`
- `.github/workflows/scientific-validation.yml`
- `src/agnxiv/validation.py`

The workflow checks out ReproRepo at the immutable commit above, runs the validation from scratch, enforces the threshold, and stores the full JSON case-level report as a CI artifact.
