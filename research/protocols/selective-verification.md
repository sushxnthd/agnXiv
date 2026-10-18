# Selective Verification and Abstention

Hypothesis: scientific verifiers should be optimized for selective correctness rather than completion.

Experiment: sweep confidence/safety gates over labeled cases and plot coverage against false-pass and total selective error.

Required outputs: confusion table including ABSTAIN, risk-coverage curve, per-stage blocker breakdown, and calibration by domain/difficulty.

Success criterion for a production safety point: maximize coverage subject to an empirical false-pass rate at or below 1% on the designated labeled evaluation set. This is a research target, not a guaranteed property.

## Statistical release gate

A measured false-pass rate of 0 is not reported as zero risk. Every selective-verification report includes a one-sided 95% upper confidence bound. For zero observed false passes, the implementation uses the exact binomial upper bound `1 - 0.05^(1/n)`, where `n` is the number of independent SUPPORTS decisions. Non-zero cases use a one-sided Wilson upper bound.

The research target “false-pass rate <= 1%” is considered statistically met only when the **upper 95% bound**, not just the empirical point estimate, is <= 1%. With zero observed false passes this requires at least **299 independent support decisions**. Repeated runs from the same evidence cluster do not count as independent decisions.
