# Selective Verification and Abstention

Hypothesis: scientific verifiers should be optimized for selective correctness rather than completion.

Experiment: sweep confidence/safety gates over labeled cases and plot coverage against false-pass and total selective error.

Required outputs: confusion table including ABSTAIN, risk-coverage curve, per-stage blocker breakdown, and calibration by domain/difficulty.

Success criterion for a production safety point: maximize coverage subject to an empirical false-pass rate at or below 1% on the designated labeled evaluation set. This is a research target, not a guaranteed property.