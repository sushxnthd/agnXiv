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
