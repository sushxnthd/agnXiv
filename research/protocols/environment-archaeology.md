# Environment Archaeology

Goal: reconstruct the minimal publication-era environment that makes a historical research artifact executable.

Compare: newest-compatible; publication-date constrained; manifest/Git-history inferred; API-signature inferred; iterative build-error repair; lineage-informed.

Metrics: build success, experiment success, result fidelity, dependency precision, repair count, wall-clock time, and unresolved ambiguity.

Do not call an environment scientifically faithful merely because it builds.

## Production holdout iteration after runtime-coverage failure

The first disjoint SciCoQA holdout achieved 30/30 dependency-source
classification accuracy but only 5/8 dependency-only environment builds
(62.5%), below the frozen 75% threshold.

Inspection showed that two failed historical repositories explicitly depend on
Python 3.7-era package stacks (including PyTorch 1.3.x / torchvision 0.4.x);
the archaeology runner had tried only Python 3.8 through 3.12. This is a
runtime-coverage defect in the recovery system, not grounds to lower the
threshold.

Accordingly:

1. Python 3.7 is added to the publication-era archaeology runtime set.
2. All 30 repository snapshots from the failed holdout are permanently added
   to the development exclusion list.
3. The next production evaluation uses the next disjoint deterministic
   SciCoQA slice under the same sampling seed.
4. The thresholds remain unchanged: at least 20 classified repositories,
   classification accuracy >= 95%, at least 8 build attempts, and build
   success rate >= 75%.

The failed holdout is retained as development evidence and cannot be reused as
held-out production evidence after this recovery change.

## Second disjoint holdout and archaeology repairs

The next disjoint SciCoQA slice again recovered dependency-source class
perfectly (30/30) but built only 5/8 dependency environments, below the frozen
75% threshold. The entire 30-repository slice is therefore retired to the
development exclusion list before further evaluation.

Two failure mechanisms were identified from that development evidence:

1. a historical repository explicitly requires Python 3.6.5, which was outside
   the prior 3.7--3.12 archaeology runtime set;
2. one repository's requirements file contains bare Python standard-library
   module names (for example `re`, `ast`, `csv`, and `unicodedata`) plus
   the common `dateutil`/PyPI-name mismatch.

The recovery procedure now adds Python 3.6 and applies only the following
frozen manifest repairs before dependency-only construction:

- drop bare `ast`, `csv`, `re`, and `unicodedata` entries;
- normalize bare `dateutil` to `python-dateutil`.

No version pins are loosened, no arbitrary package substitutions are allowed,
and the original manifest remains the provenance source. The next production
evaluation uses the next untouched deterministic SciCoQA slice. Thresholds
remain unchanged: classification n >= 20 with >=95% accuracy, at least eight
build attempts, and build success >=75%.
