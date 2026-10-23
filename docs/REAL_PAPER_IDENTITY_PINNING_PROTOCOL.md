# Frozen protocol: exact manuscript identity for real-paper verification

## Question

Can an agnXiv hosted verdict be replayed against the exact manuscript bytes that
were evaluated, or can a mutable unversioned arXiv identifier silently redirect a
future run to a different paper revision?

## Pre-implementation evidence

The successful external-paper workflow named `2604.15702` without a version,
while its evidence bundle recorded manuscript SHA-256
`f60c57f5c39453638b82b8eb1317db6b9e92d440ddf4b06eaab0a6f3a08605a7`.
arXiv currently reports two revisions and resolves the unversioned identifier to
v2. The repository was already pinned to
`2f83d0fa506e7af2b72ca191b65ce42e07c9e185`.

This asymmetry means repository identity is immutable but manuscript identity is
not. A later revision could change claims or tables while the workflow
declaration remained unchanged.

## Frozen mechanism

For hosted AUTO jobs:

1. accept an optional expected manuscript SHA-256;
2. validate its syntax before any network or repository action;
3. after download, hash the exact PDF bytes and compare in constant time;
4. on mismatch, raise a fail-closed hosted-runner error before plan discovery,
   environment building, image pulls, or scientific commands;
5. include the verified manuscript identity in both plan and verification
   results;
6. pin the external-paper workflow to `2604.15702v2` and the previously observed
   digest.

## Frozen falsification

- Matching bytes: proceed and expose the verified digest.
- Wrong digest: abort before auto planning/build/execution.
- One-byte-mutated fixture: abort before auto planning/build/execution.
- Malformed digest: abort before checkout or download.
- No expected digest: retain backward compatibility but make no exact-identity
  claim.

A unit-level call counter must show zero planner/build/scientific-execution calls
for mismatch cases. A hosted rerun must download v2, match the frozen digest, and
reproduce execution-grounded claim verdicts at the pinned repository commit.

## Strongest alternative explanation

The hash adds no value if arXiv revisions never change relevant claims or if the
unversioned endpoint is operationally stable. The two-revision history is a
direct counterexample to endpoint immutability; the hosted mismatch test
determines whether the mechanism actually blocks drift before scientific
execution.

## Kill condition

Reject the proposed pin if `2604.15702v2` does not match the previously observed
digest. Preserve that mismatch as evidence and identify the actual evaluated
revision before allowing another external-paper verdict.

## Smallest supported claim

If all gates pass, agnXiv may claim that this hosted workflow binds its verdict to
one repository commit and one exact manuscript byte string, and that a mismatch
fails before scientific execution. This does not establish historical dependency
fidelity, general paper reproducibility, sandbox isolation beyond existing
controls, or correctness of claims not evaluated by the workflow.
