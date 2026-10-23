# Result: exact manuscript identity gate for hosted real-paper verification

## Smallest supported claim

For the pinned Metacognitive Monitoring Battery reproduction, agnXiv now binds the
hosted verdict to both repository commit
`2f83d0fa506e7af2b72ca191b65ce42e07c9e185` and exact arXiv manuscript
`2604.15702v2` with SHA-256
`f60c57f5c39453638b82b8eb1317db6b9e92d440ddf4b06eaab0a6f3a08605a7`.
Malformed expectations fail before checkout. A byte mismatch fails before auto
planning, environment construction, image pulls, or scientific execution.

This closes a provenance asymmetry in which the repository was immutable but the
unversioned arXiv endpoint could move between revisions.

## Decisive evidence

- arXiv reports two revisions for 2604.15702; the prior workflow used the mutable
  unversioned identifier.
- The hosted workflow now names `2604.15702v2` and requires the exact digest
  observed in the earlier evidence bundle.
- Matching, malformed, and mutated-byte cases passed their frozen local tests.
- Mismatch call counters recorded zero planner, builder, and scientific-execution
  calls.
- The complete local suite and Ruff passed.
- Hosted run
  [40039779755](https://github.com/sushxnthd/agnXiv/actions/runs/40039779755)
  downloaded v2, matched the frozen digest, and executed against the pinned
  repository commit.
- The hosted evidence artifact digest is
  `sha256:012f224ae8bfe4beb135cb19fbe57394c6acb7f73593636d7b942f1adc14a6f4`.

The exact rerun returned two execution-grounded contradictions:

| Metric | Paper | Observed | Verdict |
| --- | ---: | ---: | --- |
| split-half r | 0.51 | 0.504 | CONTRADICTED |
| Spearman-Brown | 0.68 | 0.67 | CONTRADICTED |

These are scoped tolerance-policy verdicts, not a statement that the paper as a
whole is invalid.

## Adversarial security consequence

The first hosted security audit on implementation commit `db14f616` failed
because the newly updated vulnerability database reported three crafted-PDF
denial-of-service CVEs in the frozen `pypdf==6.21.1` service dependency. The
failure was preserved. The minimum and frozen service versions were raised to
6.21.2, the published fixed release. Security audit run
[40039779685](https://github.com/sushxnthd/agnXiv/actions/runs/40039779685)
then passed.

All eight hosted workflows at final head `8bb16732432d4b364113b763cb74fd18a4accadb`
passed: production gate, full tests, security audit, service image, external
benchmark, DeepWalk abstention, service-lock generation, and the pinned
real-paper reproduction.

## Limitations

- Exact bytes establish identity, not correctness of the manuscript or code.
- The reproduced repository environment remains floating and is explicitly
  graded as approximate rather than historically faithful.
- The artifact currently has 30-day hosted retention; this result file preserves
  its digest and compact findings, not the full execution bundle.
- The gate is optional for general AUTO requests for backward compatibility.
  Only jobs that supply an expected digest may claim exact manuscript identity.
- PR #50 remains open and conflicted with main. No merge, rebase, or force-push
  was attempted.
