# Result: exact-byte alias certificates reduce safe abstention

## Smallest supported claim

For one workflow directory containing exactly `requirements.txt` and
`requirement.txt`, equality of the two files' exact bytes is a sufficient,
independently checkable certificate that choosing the priority-ordered alias
does not discard dependency information present in the other alias. AgnXiv can
therefore resolve this case while retaining both paths and the SHA-256
certificate in its public environment record.

This is a production safety refinement, not a claim of novel dependency theory.
It replaces an avoidable abstention with a proof-carrying decision and preserves
fail-closed behavior outside the proved boundary.

## Frozen result

| Gate | Result |
| --- | ---: |
| Exact-duplicate payload families resolved | 8 / 8 |
| One-edit near-duplicates correctly abstained | 12 / 12 |
| False accepts in near-duplicate matrix | 0 |
| Independent byte/digest checks | 20 / 20 |
| Competing-manifest pairs correctly abstained | 36 / 36 |
| Singleton/root-precedence controls | 10 / 10 |
| Focused environment/auto tests | 20 / 20 |
| Full local tests | 189 / 189 |

The positive fixtures include pinned requirements, environment markers,
URL/hash references, include/constraint options, comments, an empty file, CRLF,
and non-UTF-8 bytes. The negative fixtures alter versions, markers, hashes,
options, includes, comments, whitespace, newline style, order, encoding, or the
dependency set. Even scientifically harmless byte changes abstain by design.

## Enforcement consequence

`EnvironmentSpec.manifest_equivalence_sha256` carries the proof. Resolution is
allowed only for the two supported aliases in the same directory with identical
bytes. Both manifest paths remain in `dependency_files`; the deterministic
install command targets `requirements.txt`. Any read failure, path separation,
extra manifest, cross-format pair, or byte difference returns `ambiguous` with
no install command.

The hosted production gate runs both the prior conflict matrix and the new
equivalence matrix. The raw evidence is in
`research/results/scoped-environment-equivalence.json`; the independent portion
recomputes equality and SHA-256 directly from fixture bytes without importing
the production equivalence helper.

## Threat model and limitations

- This proves exact identity at environment-inference time; it does not provide
  a filesystem immutability guarantee after inference. A later executor should
  verify the recorded digest before installation if the checkout is mutable.
- Exact bytes are deliberately stricter than semantic equivalence. Equivalent
  files that differ only by comments, whitespace, newline style, or ordering
  still abstain.
- No claim is made for Conda, Poetry, uv, setuptools, cross-directory, or
  cross-format equivalence.
- Duplicate manifests do not prove that the environment is complete,
  historically faithful, installable, or safe to execute.
- Hosted CI is a separate gate; local results do not imply that it has passed.

## Reproduction

```bash
python -m pip install -e '.[dev,pdf]'
ruff check src tests research/scripts
pytest -q
python research/scripts/verify_scoped_environment_conflicts.py
python research/scripts/verify_scoped_environment_equivalence.py
```
