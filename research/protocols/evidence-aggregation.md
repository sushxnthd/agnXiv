# Evidence Aggregation

Question: how should a living record represent multiple reproductions when attempts share code, checkpoints, data, or implementation lineage?

Represent dependencies explicitly rather than counting attempts as independent votes.

Initial ablations: naive attempt count; source-code-cluster weighting; implementation-lineage weighting; fully independent-only summary.

Output remains a structured evidence state, not a scalar truth score.