# Hosted environment-fidelity verdict firewall

## Decisive falsification

The prior real-paper workflow pinned manuscript bytes and repository code but used a floating dependency file whose inferred historical fidelity was explicitly approximate. It nevertheless published two `CONTRADICTED` scientific verdicts. Dependency drift therefore remained a live alternative explanation, so those labels exceeded the evidence.

This is a correction to the interpretation of the earlier result. The measurements remain valid observations of that hosted execution; they did not yet justify a claim of scientific contradiction.

## Enforced law

A hosted numeric decision is publishable as `VERIFIED`, `PARTIALLY_VERIFIED`, or `CONTRADICTED` only if:

1. the workflow-scoped environment is unambiguous;
2. historical dependency fidelity is constrained;
3. the actual build manifest is hash-pinned, including artifacts rather than only direct version strings; and
4. both the base and built environments have immutable image IDs.

If any condition fails, agnXiv preserves expected values, observations, errors, rationale and the raw decision as `provisional_verdict`, but publishes `UNABLE_TO_VERIFY` and a machine-readable list of blockers. Hosted job status becomes `needs_review`.

## Frozen local evidence

| Test | Result |
|---|---:|
| Adversarial gate cases | 6/6 |
| False definitive verdicts | 0 |
| Hash-pinned constrained controls preserved | 1/1 |
| Full unit suite | 199/199 |
| Ruff | clean |
| Independent stdlib-only audit | 6/6 |

The independent checker imports no production module and reproduced digest `610c38f452a8675791ccbfbe316b6a1489660961ea2008fa29ddaa7afa2497bd`.

The production gate now runs that checker. The real-paper workflow is a prospective untouched test: its two observations must remain 0.504 and 0.67, while the public decisions must become `UNABLE_TO_VERIFY` with provisional `CONTRADICTED` labels.

## Strongest alternative and controls

The specific paper computations may be invariant to the dependency changes. That is possible, but it has not been proved independently. The firewall treats unresolved environment sensitivity as an alternative explanation rather than silently assuming invariance.

The strongest positive control is a constrained, unambiguous, hash-pinned build with immutable image IDs. It retains the original decisive numeric verdict. Direct `package==version` pins intentionally fail the control because they need not pin transitive artifacts. A mixed manifest with one hashed and one unhashed package also fails; the classifier now requires a valid 64-hex SHA-256 for every logical requirement.

## Direct product consequence

A hosted job can no longer turn a result from an underdetermined runtime into a public scientific verification or contradiction. Reviewers still receive the full measurement and provisional comparison, so abstention does not erase evidence.

## Limits and smallest claim

This mechanism establishes a necessary publication boundary, not sufficient proof of reproduction. Hashes identify an environment but do not prove it matches an author's unpublished historical runtime. The firewall also does not certify datasets, code semantics or automatic claim extraction.

Smallest supported claim before hosted validation: the local production boundary and an independent checker suppress definitive hosted verdicts for every frozen underdetermined-environment case while preserving observations, and do not suppress the exact positive control.

## Hosted prospective validation

The untouched real-paper workflow matched the prediction at
[run 40116884857](https://github.com/sushxnthd/agnXiv/actions/runs/40116884857),
head `4cea106867a53377ea264b070e79ce11b5ddcd5a`.  Its exact artifact archive
(`12569325839`, SHA-256
`fce92fdc1ced72366437cad6830c043520870abbc299a54cb00fdb0e6c3f94cb`)
preserved both measurements: 0.504 versus 0.51 and 0.67 versus 0.68.  Both
public verdicts became `UNABLE_TO_VERIFY`; both raw numeric decisions remained
`provisional_verdict=CONTRADICTED`; job status became `needs_review`.

`research/scripts/audit_real_paper_hosted_artifact.py` independently verifies
the archive bytes, manuscript identity, repository commit, immutable execution
identity, unchanged source tree, both observations and every fail-closed reason
without importing agnXiv production code.  This closes the preregistered hosted
gate.  It does not upgrade either provisional comparison to a scientific
contradiction.

The exact 21,398-byte GitHub artifact is preserved at
`research/evidence/hosted-real-paper/run-40116884857.zip`, so the audit remains
replayable after GitHub's temporary artifact retention expires.
