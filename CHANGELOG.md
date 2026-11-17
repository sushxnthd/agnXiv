# Changelog

All notable user-facing changes are recorded here. AgnXiv follows semantic
versioning; entries under **Unreleased** are release-candidate changes and are
not claims about the existing public artifact.

## Unreleased

No changes yet.

## 0.2.0 - release candidate

This section describes the candidate artifacts on the research branch. It is
not a claim that v0.2.0 has been tagged or published.

### Added

- `agnxiv doctor` reports Git, PDF, Docker CLI, and Docker daemon readiness
  with machine-readable remediation.
- `agnxiv verify-external` provides one stable command for a pinned public
  arXiv manuscript and GitHub repository, from intake through sandboxed
  measurement and an exportable JSON audit record.
- Setup failures are exported before repository download or scientific
  execution, while conservative scientific abstentions remain successful
  completed workflows.
- A clean-runner GitHub acceptance workflow exercises the CLI against the
  pinned metacognitive-monitoring battery example and preserves its audit
  artifact.
- The manual v0.2.0 publication path now uses a checked-in fail-closed policy
  before draft creation and before publication. Exhaustive adversarial matrices
  reject all 61 unsafe preflight states and all 1,023 mutated post-draft states
  with zero false passes, while an independent audit verifies workflow order.

### Security

- The frozen service environment requires `opentelemetry-api==1.45.2` and
  `pypdf==6.21.4`, closing the eight vulnerabilities reported by the
  exact-head dependency audit.
- The digest-pinned service image upgrades and version-checks `apt` and
  `libapt-pkg6.0` at build time, in addition to the existing OpenSSL checks.

### Known release blockers

- The exact-head release-candidate workflow has built, clean-installed, and
  exercised the wheel against the pinned external-paper example.
- PR #50 remains draft and unmerged; no automatic merge is authorized.
- Public release requires independent review and a manual `publish-v0.2.0`
  dispatch naming the exact current candidate commit. The workflow creates a
  draft, re-downloads and hash-checks every asset, clean-installs the downloaded
  wheel, and only then publishes the release.
- Docker remains an explicit prerequisite for local sandboxed execution.

## 0.1.0 - 2026-10-19

- First public Python wheel and source release.
- Declarative claim verification, evidence fingerprinting, Docker isolation,
  explicit observation locators, in-toto statements, and optional DSSE
  signing.
- Public release artifact installation is verified, but the stronger
  end-to-end external-paper acceptance gate was not part of this tag.
