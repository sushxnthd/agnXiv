# Release process

AgnXiv releases are generated only from `main` by
`.github/workflows/release.yml`.

## Contract

1. The version in `pyproject.toml` and `src/agnxiv/__init__.py` must match
   stable Semantic Versioning.
2. `CHANGELOG.md` and `docs/releases/v<version>.md` must exist before merge.
3. The mainline commit must be cryptographically verified and associated with a
   merged pull request.
4. External GitHub Actions must be pinned to immutable commit SHAs and checkout
   credentials must not persist.
5. The full test suite, scientific safety benchmarks, reproducible package
   build, package metadata check, service-image vulnerability scan, SBOM
   generation, and release contract must pass.
6. Release artifacts receive SHA-256 checksums and GitHub build-provenance
   attestations.
7. The workflow creates an annotated `v<version>` Git tag and a GitHub Release.
8. If a release for the current version already exists, subsequent mainline
   commits do not create another release. A new release requires an explicit
   version bump and matching changelog/release notes.

## Version changes

Version bumps should be isolated and reviewed. Do not reuse or move an existing
release tag. Do not overwrite release assets. If a tag exists without a GitHub
Release, the workflow fails closed rather than guessing how to recover.

## Main branch policy

Repository automation rejects release of direct/unverified mainline commits,
and `.github/workflows/mainline-policy.yml` flags any main commit that is not
a verified merged-PR commit.

GitHub branch protection/rulesets are an account-level control and should also
require pull requests, block force-pushes/deletion, require signed commits, and
require the production/test/security/release-policy checks. The repository
connection used by ChatGPT does not expose administration writes, so the
desired rules are documented in `docs/MAIN_BRANCH_RULESET.md`.
