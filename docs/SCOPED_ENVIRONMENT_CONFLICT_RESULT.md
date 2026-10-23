# Scoped-environment conflict boundary

## Decisive falsification

PR #50 correctly abstained when different selected workflow sources resolved to
different manifests, but it silently chose the first filename when multiple
manifests occupied the *same* nearest workflow directory.  A pinned
`requirements.txt` beside an incompatible `environment.yml` was reported as a
resolved, historically constrained environment.  The competing Conda
environment disappeared from the plan.

That behavior violated the PR's stated trust boundary.  Filename priority is a
search heuristic, not scientific evidence that one environment generated the
paper result.

## Enforcement change

The resolver now preserves every manifest found at the nearest workflow scope.
One candidate resolves normally.  Two or more candidates produce
`scope_resolution=ambiguous`, no preferred manifest, no install command, and an
auto-plan blocker before dependency installation or research execution.

Root metadata can no longer overwrite the dependency precision, historical
fidelity, dependency list, or install command of a resolved nested workflow
environment.  This closes a related provenance error where a pinned root
requirements file could make the plan describe an actually selected floating
nested manifest as version-pinned.

## Frozen evidence

The adversarial matrix covers every unordered pair of the nine supported
manifest filenames in one workflow directory:

- 36/36 conflicts abstained.
- Zero conflict false accepts.
- 9/9 single-manifest controls remained resolved.
- The root-versus-nested scope-precedence control remained operational.
- Focused environment and auto-plan regression tests passed.

The matrix is exact over filename pairs, not sampled.  Its JSON artifact records
each resolution, preferred file, install-command set, and pass/fail decision.

## Direct product consequence

AgnXiv will sacrifice coverage when a repository exposes co-located dependency
descriptions that might be complementary.  That is deliberate: until it can
prove that two files belong to one lock graph, it does not execute either as the
paper's environment.  A future typed resolver may safely recognize explicit
lock/manifest pairs, but filename convention alone is insufficient.

## Smallest supported claim

For the supported static manifest filenames and selected Python workflow scope,
agnXiv no longer converts co-located environment ambiguity into a trusted
execution choice.  It fails closed and keeps root metadata from upgrading the
reported fidelity of a nested environment.

This is a production safety result, not a scientific reproduction result.  It
does not establish historical dependency fidelity, package compatibility,
microVM isolation, or correct paper claims.

