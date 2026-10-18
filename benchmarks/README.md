# AgnXiv Benchmarks

AgnXiv benchmarks are designed around **false-pass resistance**, not badge count.

## Core adversarial benchmark

`benchmarks/core.jsonl` contains captured-output cases that test:

- correct reproduction;
- clear contradiction;
- answer-value decoys;
- ambiguous unlabeled outputs;
- metric-name numeric decoys.

CI requires zero false passes on this suite.

## External research benchmark

The external workflow pins:

- repository: `Pranavsingh431/Perturbation-Based-Measurements`;
- commit: `d7fa58215bf6966df70d05f5433f1238c05d2ea0`;
- target artifact: `results/paper_numbers.json`;
- target claim: Pool A gap G on the 15–85 baseline band, reported as 26.6.

The repository states that `evaluation/reproduce.py` checks 96 reported quantities from released raw outputs.

### Broad reproduction audit

Under the environment reconstructed from the repository's current `requirements.txt`, the released all-in-one checker currently exits nonzero:

- 94/96 checks pass;
- AUC confidence alone is recomputed as 0.546 versus reported 0.647;
- incremental AUC gain is recomputed as +0.115 versus reported +0.011.

AgnXiv therefore emits **UNABLE_TO_VERIFY** for the blanket "96/96" reproduction claim. It does not ignore the nonzero exit code or cherry-pick the passing lines.

The dependency manifest is classified as **floating** because it uses lower bounds such as `numpy>=1.24` rather than an exact historical lock. The benchmark does not assert that dependency drift is the only possible cause of the AUC mismatch; it records the exact source, runtime image, output hashes, and observed failure.

### Independent claim verification

AgnXiv then executes `benchmarks/adapters/perturbation_pool_a.py`, an independent adapter that does not import the authors' evaluation code. It reads only the released raw result JSON and directly implements the published target statistic:

- contested Pool-A items only;
- neutral baseline strictly between 15 and 85;
- directional spread from reads 1–4;
- rewording spread from the first four rewording reads;
- mean directional-minus-rewording spread.

That independent computation reproduces the reported central effect within the declared absolute tolerance and receives **VERIFIED**.

The resulting statement binds:

- the pinned external Git commit;
- the external repository tree digest;
- the independent adapter digest;
- the frozen paper-number artifact digest;
- the immutable runtime image ID;
- the declared observation locator and policy;
- the executed output digest.

The statement is DSSE-signed in CI and independently verified with the corresponding public key.

## Interpretation

This benchmark demonstrates the intended scope of AgnXiv:

**A paper is not forced into one global pass/fail badge.**

A broad reproduction workflow may be incomplete while a narrower claim remains reproducible. AgnXiv records those facts separately and refuses to upgrade the narrower success into a stronger claim.
