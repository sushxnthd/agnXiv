# Frozen protocol: comment-smuggled dependency hashes

Status: frozen before correction and adversarial execution.

## Question

Can agnXiv classify a pip requirement as `hash-pinned` when its apparent
`--hash=sha256:...` token occurs only inside a comment, allowing mutable package
artifacts to cross the definitive-verdict firewall?

## Observed counterexample

`package==1.0 # --hash=sha256:<64 hex characters>` is currently classified as
`hash-pinned`. Pip discards the inline comment, so the effective requirement is
unhashed and the generated build does not explicitly enable `--require-hashes`.

## Proposed enforcement

1. Remove requirement-file comments before parsing logical requirements and
   hash tokens.
2. Classify a logical requirement as hash-pinned only when an effective,
   non-comment SHA-256 token remains.
3. Whenever a plan is classified `hash-pinned`, generate the install command
   with explicit `python -m pip install --require-hashes ...` enforcement.
4. Keep version-pinned or floating manifests buildable for conditional evidence,
   but prevent them from authorizing definitive scientific verdicts.

## Frozen gates

- At least 128 comment-smuggling variants; the old classifier must accept every
  attack and the corrected classifier must reject every one.
- At least 32 genuine single-line and continued-line hash controls must remain
  hash-pinned and receive explicit runtime enforcement.
- Test whitespace, tabs, multiple packages, mixed real/fake hashes, comments
  containing continuations, upper/lower hex, and trailing text.
- Independent stdlib-only checker with zero production imports.
- Full regression, deterministic evidence, Ruff, diff check, and hosted CI.

## Smallest supported claim

The correction may claim only that comment text cannot satisfy agnXiv's
dependency-hash evidence requirement and that accepted hash-pinned plans invoke
pip's hash-checking mode explicitly. It does not establish package-index
authenticity, hash collision resistance beyond SHA-256 assumptions, historical
environment equivalence, sandbox isolation, or scientific correctness.
