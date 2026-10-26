# Hosted callbacks now bind the complete scientific object

## Result

The service callback previously authenticated the GitHub Actions worker,
checked the pinned repository commit, and verified that `auto_planned`
authority matched the submitted frozen locator digest. Those checks did not
bind the result to the requested arXiv manuscript or require the locator's
claim identity to match its bundle.

A structurally valid result from another manuscript or claim could therefore
be replayed into a job sharing the same repository commit. Recomputing the
locator digest preserved internal consistency and did not expose the
substitution.

The callback now enforces one chain:

`job arXiv ID -> callback manuscript identity -> every bundle manuscript -> frozen locator claim -> bundle claim`.

The earlier repository-commit, clean-checkout, authority, locator-digest, and
status checks remain in force.

## Frozen adversarial evidence

The preregistered matrix contained 128 instances of each attack family:

| Attack | Old boundary accepted | Corrected boundary accepted |
|---|---:|---:|
| Cross-arXiv identity | 128/128 | 0/128 |
| Cross-manuscript digest | 128/128 | 0/128 |
| Cross-manuscript additional bundle | 128/128 | 0/128 |
| Cross-claim locator with recomputed digest | 128/128 | 0/128 |
| Cross-metric locator with recomputed digest | 128/128 | 0/128 |

All 32 coherent controls remained accepted and retained their exact decisive
verdicts. An independent standard-library-only audit reproduced all 640 old
false accepts, all 640 corrected rejections, the case digest, and all controls
while importing zero agnXiv modules.

The earlier authority-evidence and preserved real-paper migration gates were
rerun after the correction and remained green.

## Reproduction

```bash
python research/scripts/verify_callback_scientific_object_binding.py
python research/scripts/audit_callback_scientific_object_binding.py
pytest -q tests/test_service_hardening.py
```

Raw evidence is stored in:

- `research/results/callback-scientific-object-binding.json`
- `research/results/callback-scientific-object-binding-audit.json`

## Bounded conclusion

This closes cross-job and cross-claim replay at the authenticated callback
boundary. It does not establish the scientific correctness of an auto-planned
procedure, provide independent reviewer authority, or pin an arXiv document
across time when the job itself does not carry an expected manuscript digest.
Those remain separate production gates.
