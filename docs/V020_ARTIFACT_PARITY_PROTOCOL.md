# Protocol: v0.2.0 source-to-wheel artifact parity

## Release question frozen before implementation

The release candidate currently builds a wheel and source distribution from one
checkout and hashes both.  That does not prove that the published source
distribution reconstructs the published wheel.  Can the release gate safely
extract the sdist, rebuild it with the pinned backend, and require exact wheel
identity before either candidate acceptance or public release?

## Prospectively frozen prediction

At the current persistent research-branch head, after pinning the build backend
to `hatchling==1.33.0`:

1. the checkout-built `agnxiv-0.2.0-py3-none-any.whl` and the wheel rebuilt
   from `agnxiv-0.2.0.tar.gz` will be byte-identical;
2. both wheels will have the same SHA-256 and internally valid `RECORD` hashes;
3. the sdist will contain only regular files and directories below the single
   `agnxiv-0.2.0/` root, with no link or path-traversal member;
4. the wheel will contain version `0.2.0`, the `agnxiv` console entry point,
   and the expected CLI module;
5. the candidate and publication workflows will emit and preserve a
   commit-bound artifact-parity report; and
6. the post-draft publication matrix will expand from ten to twelve toggled
   invariants (4,096 states), accepting only the valid control with zero false
   passes and zero false rejects.

## Falsification

Any extraction-safety failure, metadata mismatch, invalid or incomplete wheel
`RECORD`, non-identical rebuilt wheel, report/commit mismatch, report/payload
hash mismatch, workflow-order violation, false pass, or false reject falsifies
the gate.  Preserve failures rather than weakening equality to a looser file
subset check.

## Product consequence

A passing result closes one concrete public-release supply-chain gap: an
external user can verify that the released sdist reconstructs the exact released
wheel payload under the pinned build backend.  It does not authorize publishing
v0.2.0, merge draft PR #50, establish runner trust, publish to PyPI, or claim a
hosted deployment.
