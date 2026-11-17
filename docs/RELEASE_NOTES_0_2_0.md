# agnXiv v0.2.0

This release provides a narrow, end-to-end CLI for reproducing one declared
computational claim from a pinned public paper and repository while preserving
conservative abstention.

## Install

Python 3.11 or newer, Git, and a running Docker daemon are required for the
sandboxed external-paper workflow.

```bash
python -m pip install \
  "agnxiv[pdf] @ https://github.com/sushxnthd/agnXiv/releases/download/v0.2.0/agnxiv-0.2.0-py3-none-any.whl"
agnxiv doctor
```

## Reproduce the public example

```bash
agnxiv verify-external \
  --repository synthiumjp/metacognitive-monitoring-battery \
  --repository-ref 2f83d0fa506e7af2b72ca191b65ce42e07c9e185 \
  --arxiv-id 2604.15702v2 \
  --expected-manuscript-sha256 \
    f60c57f5c39453638b82b8eb1317db6b9e92d440ddf4b06eaab0a6f3a08605a7 \
  --output agnxiv-v0.2.0-example-audit.json
```

The frozen acceptance run measures `0.504` for a paper-reported `0.51`. It
retains the final verdict `UNABLE_TO_VERIFY` because the reconstructed
environment does not justify a stronger scientific conclusion. The narrower
provisional numeric comparison is preserved as `CONTRADICTED` in the exported
audit record.

## What changed

- `agnxiv doctor` reports Git, PDF, Docker CLI, and Docker daemon readiness.
- `agnxiv verify-external` covers claim intake, repository/environment
  resolution, sandboxed execution, evidence bundling, conservative verdict,
  and an exportable JSON audit record in one command.
- Setup failures are exported before scientific execution.
- Public distributions are bound to the exact release commit and audit-record
  hashes in `agnxiv-v0.2.0-release-manifest.json`.

## Security and limitations

Research repositories are untrusted code. Execution uses Docker with network
isolation, dropped capabilities, resource limits, and immutable evidence
fingerprints. Read `SECURITY.md` before verifying unfamiliar artifacts.

agnXiv does not certify an entire paper, novelty, significance, misconduct, or
universal truth. It evaluates only explicit computational claims under the
recorded source, runtime, locator, and policy. Ambiguous evidence abstains.
This release does not claim PyPI publication or a hosted verification service.
