# AgnXiv Competitive Position — 2026-10-19

AgnXiv should not claim to be universally "better" than every reproducibility product. The goal is to win a narrower category: **execution-grounded, claim-level scientific verification with conservative abstention and auditable evidence provenance.**

## Current landscape

| System | Strongest capability | AgnXiv must not imitate poorly | AgnXiv win condition |
|---|---|---|---|
| Code Ocean | Preserved compute capsules, browser execution, DOI/publisher integrations | Mature capsule hosting and publisher workflow | Verify public paper/repository pairs with less author packaging, and produce claim-level signed evidence rather than only a runnable capsule |
| PaperBench | Author-vetted full-paper replication benchmark with granular rubrics | Breadth/depth of from-scratch replication scoring | Use PaperBench-style process rigor as an evaluation source while keeping production verdicts deterministic and evidence-bound |
| ReproRepo | Large-scale realistic reproducibility-blocker discovery from GitHub issues | Scale of paper/repository audit data | Add actual isolated execution and claim-level observation evidence where safe, while retaining abstention when execution semantics are unresolved |
| AI4Reproducibility | Structured automated reproducibility audit and deterministic static checks | Rich reviewer-style audit surface | Combine static audit signals with execution, immutable provenance, answer-blind output selection, and signed records |
| AgnXiv | Zero-manifest claim execution, answer-blind locator freezing, abstention, DSSE/in-toto provenance, living evidence records | — | Demonstrate lower false-pass risk at useful coverage on held-out papers, then scale across domains |

## Product moat to build

AgnXiv's defensible moat is not "AI reviews papers." It is the conjunction of:

1. paper and repository pinned to exact identities;
2. dependency/runtime reconstruction with explicit fidelity labels;
3. no-network isolated execution;
4. observation locator selected without access to the reported answer;
5. deterministic claim-level comparison policy;
6. source/artifact mutation checks;
7. signed machine-readable verification statements;
8. abstention when any safety-critical link is ambiguous;
9. multiple attempts aggregated by evidence independence, not vote count;
10. public challenge/response/rerun history.

## Must-win metrics

AgnXiv may claim category leadership only after measuring:

- empirical false-pass rate with confidence intervals on a held-out benchmark;
- verification coverage at a fixed false-pass target;
- real-paper execution success rate;
- blinded locator accuracy on held-out outputs;
- central-claim recall@k;
- critical-path recall for claim-evidence DAGs;
- historical environment recovery rate;
- intervention rate and wall-clock cost;
- cross-domain coverage;
- percentage of public verdicts backed by strong rather than conditional evidence.

## Current disadvantages

AgnXiv is currently behind mature platforms on:

- publisher integrations and institutional adoption;
- durable artifact storage and DOI issuance;
- GPU/hardware scheduling;
- private/confidential manuscript execution;
- long-horizon full-paper reimplementation;
- dataset/checkpoint registry integrations;
- operational SLO history at production traffic;
- held-out benchmark scale.

These gaps are roadmap items, not marketing language to hide.

## Sources used for this comparison

- OpenAI PaperBench: https://openai.com/index/paperbench/
- IEEE reproducibility / Code Ocean guidance: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/research-reproducibility/
- ReproRepo: https://arxiv.org/abs/2606.18237
- AI4Reproducibility: https://github.com/sistm/AI4Reproducibility
