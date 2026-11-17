# v0.2.0 publication-gate adversarial result

## Product consequence

The manual v0.2.0 publisher now delegates its security-critical decisions to a
checked-in executable policy.  The same policy is exercised offline by tests,
used by the GitHub workflow before draft creation and before publication, and
independently audited without importing the primary implementation.

This closes a release-review gap: authorization and asset safety are no longer
only shell fragments that reviewers must mentally reconstruct.

## Fail-closed preflight

Publication authorization requires all of the following:

- the exact confirmation phrase `PUBLISH v0.2.0`;
- a lowercase 40-character candidate commit;
- equality between that candidate and the current persistent research-branch
  head;
- no existing public release; and
- if a draft or tag already exists, exact binding to the candidate commit.

The exhaustive matrix covered 64 combinations of confirmation, commit format,
branch-head equality, release state, and target binding.  Exactly three safe
controls passed: no existing tag/release, a matching draft, and a matching
tag-only recovery state.  All 61 unsafe states were rejected.

| Matrix | Cases | Accepted controls | Rejected | False passes | False rejects |
|---|---:|---:|---:|---:|---:|
| Preflight authorization | 64 | 3 | 61 | 0 | 0 |

## Fail-closed draft-asset gate

After the workflow creates or repairs a draft release, publication requires:

- exactly four named release assets, with no missing, duplicate, partial, or
  extra asset;
- exact GitHub metadata sizes for all downloaded assets;
- manifest schema, version, tag, candidate commit, and draft-only state;
- final conservative verdict `UNABLE_TO_VERIFY` and `false_pass=false`;
- exactly the wheel, source distribution, and external audit in the manifest;
  and
- exact payload sizes and SHA-256 hashes.

The post-draft matrix independently toggled ten safety invariants, covering all
1,024 combinations.  Only the all-valid state passed.  Every one of the 1,023
mutated states was rejected.

| Matrix | Cases | Accepted controls | Rejected | False passes | False rejects |
|---|---:|---:|---:|---:|---:|
| Draft assets and manifest | 1,024 | 1 | 1,023 | 0 | 0 |

The independent audit also verifies workflow order:

`preflight -> draft creation -> asset gate -> public release`.

The public transition is unreachable before both executable gates complete.

## Reproducibility

```bash
python scripts/verify_v020_release_publication_gate.py matrix
python scripts/audit_v020_release_publication_gate.py
pytest -q tests/test_v020_publication_workflow.py \
  tests/test_v020_release_publication_gate.py
```

- Primary result SHA-256:
  `e54e5369ee516a1d0a2c84fedb3364cabb65645b62a2c8d44db2b5c6ae263b8a`.
- Independent audit SHA-256:
  `3c899c5852e05bd080c095ca014df49f1256e38b503d6975daf5675fb0b83b6b`.
- Deterministic reruns were byte-identical.
- Both targeted tests and Ruff passed locally.

## Boundaries

This proves the behavior of the modeled release authorization and asset states;
it does not prove GitHub, the runner, or repository administrators are honest.
The workflow still requires an explicit manual dispatch and the
`agnxiv-release` environment.  It does not publish to PyPI or deploy a hosted
service.  No v0.2.0 tag or release was created by this experiment, and draft PR
#50 remains unmerged.
