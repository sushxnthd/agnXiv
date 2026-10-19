# Historical environment recovery validation v1 — 2026-10-19

**Status:** PASS  
**Evaluation role:** heldout_external_historical_environment  
**CI run:** 39225677632  
**Validated commit:** `9ca32bb5949854dcd9c340f6b30b8899e1bac966`

## Frozen production gate

The environment-recovery gate requires, on a disjoint held-out slice:

- at least 20 dependency-source classification cases;
- dependency-source classification accuracy >= 95%;
- at least 8 dependency-only environment construction attempts;
- build success rate >= 75%.

Thresholds were not loosened after failures. Two earlier held-out slices that
exposed recovery defects were moved permanently into the development exclusion
set before the final evaluation.

## External source and separation

- Dataset: SciCoQA v1.1
- Repository: `UKPLab/scicoqa`
- Pinned commit: `463162906459be508ed4a2294fcaede9fa072036`
- Sampling seed: `agnxiv-env-heldout-v1`
- Development-excluded repository snapshots before final run: 90
- Remaining candidate repository snapshots: 186

The final production slice was selected only after excluding every repository
snapshot used to diagnose the previous failures.

## Recovery improvements frozen before the passing holdout

Earlier development slices exposed two concrete archaeology gaps:

1. publication-era projects explicitly requiring Python 3.6 were outside the
   runtime search set;
2. some historical requirements files contain bare standard-library module
   names or the common `dateutil` / `python-dateutil` package-name mismatch.

Before the final untouched holdout, the recovery procedure was frozen to add
Python 3.6 and only these conservative manifest repairs:

- drop bare `ast`, `csv`, `re`, and `unicodedata` dependency entries;
- normalize bare `dateutil` to `python-dateutil`.

No dependency version pin is loosened by these repairs.

## Final held-out result

| Metric | Result | Gate |
| --- | ---: | ---: |
| Dependency-source cases | 31 | >= 20 |
| Correct dependency-source classifications | 30/31 | — |
| Classification accuracy | **96.77%** | >= 95% |
| Dependency-only build attempts | 8 | >= 8 |
| Successful builds | 7/8 | — |
| Build success rate | **87.5%** | >= 75% |
| Release result | **PASS** | PASS |

The complete report was emitted as
`agnxiv.historical-environment-validation/1` and archived by GitHub Actions.

## Interpretation boundary

This validates AgnXiv's **dependency-source recovery and dependency-only
environment construction** on the bounded public-beta archaeology benchmark.
It does not prove exact publication-era equivalence, successful execution of
every full experiment, GPU/CUDA compatibility, or historical dataset/checkpoint
availability. Those uncertainties remain reflected in the evidence-strength
model: reconstructed or floating environments must not be promoted to STRONG
publication-era evidence without stronger provenance.
