# Workflow-scoped environment conflict protocol

## Frozen question

Does agnXiv abstain whenever one selected reproduction workflow is adjacent to
multiple plausible dependency manifests, or can filename priority silently
choose an environment that changes the scientific execution?

## Threat model

A real research repository may contain `requirements.txt`, a Conda environment,
an alternate `requirement.txt`, or lock/package metadata in the same workflow
directory.  Their dependency sets and Python versions may disagree.  File-name
priority is not evidence that one environment generated the paper result.

An attacker or accidental repository layout can therefore place a convenient
version-pinned requirements file beside an incompatible environment manifest.
If agnXiv silently selects the requirements file, a clean numeric reproduction
could be executed in the wrong environment.

## Frozen falsification cases

1. `requirements.txt` plus an incompatible `environment.yml` in the selected
   workflow directory.
2. `requirements.txt` plus a conflicting `requirement.txt` in that directory.
3. Two selected workflow sources that resolve to the same pair of conflicting
   manifests.
4. A single unambiguous nested requirements file as the operational control.
5. A root manifest plus one unambiguous nested manifest as the scope-precedence
   control.

## Required result

Cases 1--3 must return `scope_resolution=ambiguous`, no preferred manifest, and
no install command.  Auto planning must retain the ambiguity blocker and must
not become safe to execute.  Cases 4--5 must remain resolved and operational.

## Kill condition

Reject the mechanism if any conflicting-manifest case is resolved, if the
ambiguity disappears during serialization, or if either operational control
is incorrectly blocked.

## Claim boundary

This protocol tests conservative static selection only.  It does not establish
publication-era environment fidelity, dependency compatibility, secure package
installation, or successful reproduction of a paper.

