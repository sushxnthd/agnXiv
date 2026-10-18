# AgnXiv

**AgnXiv turns claims in computational research papers into executable tests.**

The first milestone is deliberately narrow:

> **PDF + research repository → quantitative claim → executable evidence → auditable verdict**

AgnXiv is not an acceptance predictor and does not certify that a paper is universally “correct.” It verifies narrower statements against explicit evidence and policies.

## Verification verdicts

- **VERIFIED** — reproduced evidence satisfies the declared verification policy.
- **PARTIALLY_VERIFIED** — only part of the claim could be reproduced.
- **CONTRADICTED** — reproduced evidence conflicts with the reported claim.
- **UNABLE_TO_VERIFY** — there is not enough executable evidence to make a reliable determination.

## Architecture

1. **Claim Compiler** — extracts material quantitative claims from a manuscript.
2. **Evidence Mapper** — links claims to figures, tables, outputs, scripts, code and data.
3. **Execution Engine** — runs the mapped workflow in an isolated environment.
4. **Verification Policy** — deterministically compares reported and observed evidence.
5. **Verification Record** — emits a version-bound, machine-readable audit record.
6. **Challenge Engine** *(next)* — performs robustness and falsification tests.

## MVP status

The repository begins with the deterministic core: claim structures, numeric comparison policies, record generation, and a CLI. PDF parsing and autonomous repository execution are layered on top rather than mixed into the source of truth.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
agnxiv --help
```

## Core principle

**Models may discover what to test. Execution determines what happened.**
