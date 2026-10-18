# Evidence Aggregation

Question: how should a living record represent multiple reproductions when attempts share code, checkpoints, data, or implementation lineage?

Represent dependencies explicitly rather than counting attempts as independent votes.

Initial ablations: naive attempt count; source-code-cluster weighting; implementation-lineage weighting; fully independent-only summary.

Output remains a structured evidence state, not a scalar truth score.

## v1 implemented semantics

Each claim is aggregated separately. Attempts are grouped into evidence clusters by bound source commit and declared external artifact identities; repeated runs inside one cluster do not become independent votes.

Evidence strength is separated from the raw numeric verifier verdict:

- **STRONG** — explicit locator, clean immutable execution, and base-only/locked/version/hash-pinned dependencies.
- **CONDITIONAL** — explicit clean execution, but environment fidelity is floating or otherwise insufficient for publication-era equivalence.
- **INCONCLUSIVE** — execution or observation semantics are not strong enough for a decided evidence state.

A contradiction and reproduction inside the same cluster is a **CLUSTER_CONFLICT**, not mixed independent evidence. Independent STRONG clusters that disagree produce **MIXED_EVIDENCE**. CONDITIONAL evidence is retained but does not overrule a STRONG cluster state.

The executable regression cohort is in research/benchmarks/aggregation-v1.jsonl and is run by research-aggregation CI.
