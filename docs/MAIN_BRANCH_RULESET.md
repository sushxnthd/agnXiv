# Required main-branch ruleset

Apply these settings to `main` in GitHub repository rules or branch protection:

- require a pull request before merging;
- require at least one approval when multiple maintainers are active;
- dismiss stale approvals after new commits;
- require conversation resolution;
- require signed commits;
- block force pushes;
- block branch deletion;
- require branches to be up to date before merging;
- require these status checks:
  - `test`;
  - `safety-contract` from `production-gate`;
  - `static-analysis` and `python-dependencies` from `security-audit`;
  - `codeql` from `external-security-review`;
  - `archive-contract` and `live-registry-smoke` from `evidence-integrity`;
  - `verified-pr-merge` from `mainline-policy` where GitHub permits a
    post-merge policy check to be selected;
- do not allow bypasses except emergency repository administrators.

The repository itself independently refuses to publish a release from a commit
that is unverified or is not associated with a merged pull request.
