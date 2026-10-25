# Base-image identity coherence result

## Result

agnXiv previously obtained a mutable base tag's image ID and repository digest
in two independent calls. A concurrent A-to-B-to-A retag could make those calls
observe different images: the Dockerfile was correctly bound to digest B, but
the resulting audit record carried canonical image ID A. The endpoint ID check
still passed because the tag returned to A after the build.

The builder now resolves the repository digest first and derives both the pre-
and post-build base IDs from that immutable reference. The mutable tag can no
longer supply the audited base ID. Malformed identities fail before Docker
execution, and a changed identity for the same immutable reference fails after
the build.

## Frozen evidence

| Gate | Result |
|---|---:|
| Split-resolution A-to-B-to-A attacks | 128 |
| Old baseline false accepts | 128 / 128 |
| Corrected coherent bindings | 128 / 128 |
| Mutable-tag ID lookups after correction | 0 |
| Unchanged controls preserved | 16 / 16 |
| Malformed bound IDs rejected before build | 4 / 4 |
| Post-bind immutable-ID mismatches rejected | 16 / 16 |
| Independent cases reproduced | 144 / 144 |
| Independent production imports | 0 |
| Repository regression | 219 / 219 |
| Primary digest | `c1ab3c7af886423afc929643687430e456515aeb26b2e12015da7d15ca0dfc80` |

The independent checker uses only the Python standard library, validates every
canonical ID and digest-reference shape, distinguishes all 128 attacks from 16
matched controls, and reproduces the primary case digest.

## Product consequence

Every successful `BuildResult` now records the content ID of the exact immutable
base reference serialized into its Dockerfile. This removes an internal
contradiction that the hosted verdict gate previously could not detect because
both unrelated IDs were individually well formed.

## Limits and novelty boundary

Immutable digest pinning and content-addressed image identities are established
container supply-chain mechanisms. The bounded contribution is discovery,
adversarial reproduction, and closure of this split-resolution provenance race
in agnXiv's scientific-verdict path.

The result assumes honest SHA-256 computation and a Docker daemon that answers
immutable-reference inspection consistently. It does not establish registry or
daemon integrity, image safety, dependency correctness, sandbox isolation, or
scientific correctness.

## Reproduction

```bash
PYTHONPATH=src python research/scripts/verify_base_identity_coherence.py
python research/scripts/audit_base_identity_coherence.py
uv run --extra dev --extra pdf pytest -q
uv run --extra dev --with ruff ruff check src tests research/scripts
```

Both evidence files reproduced byte-for-byte; Ruff and the whitespace-error
check passed on the complete changed tree.
