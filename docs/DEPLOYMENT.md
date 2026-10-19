# Production Deployment Runbook

This runbook is the minimum safe sequence for the hosted AgnXiv control plane.
A successful CI run is necessary but does not make an undeployed service production-grade.

## 1. Select the release commit

Release only a commit on `main` for which all required workflows are green:

- `test`
- `production-gate`
- `static-security`
- `security-audit`
- `service-image`
- `postgres-restore-drill`
- `zero-manifest-real-paper`
- `external-benchmark`
- `deepwalk-auto`
- `release-provenance`

Record the 40-character release commit SHA. Create an immutable release tag at that exact commit, for example `agnxiv-release-2026-10-19.1`. The release-provenance workflow must produce a GitHub/Sigstore attestation for `agnxiv-release-manifest.json`.

## 2. Provision the production dependencies

Use a managed PostgreSQL database with provider backups enabled. Do not use
SQLite in production. Generate:

- an API key with at least 32 random characters;
- an Ed25519 issuer keypair, keeping the private key outside the repository;
- a GitHub token scoped only to dispatch Actions in the AgnXiv repository.

The service must have HTTPS before readiness can become green.

## 3. Configure the control plane

Required settings:

```text
DATABASE_URL=postgresql+psycopg://...
AGNXIV_API_KEYS=<high-entropy-key>
AGNXIV_PUBLIC_BASE_URL=https://<service-host>
AGNXIV_GITHUB_TOKEN=<actions-dispatch-token>
AGNXIV_GITHUB_REPOSITORY=sushxnthd/agnXiv
AGNXIV_GITHUB_REF=refs/tags/agnxiv-release-<version>
AGNXIV_GITHUB_WORKFLOW=hosted-verify.yml
AGNXIV_GITHUB_WORKFLOW_SHA=<40-char release commit SHA>
AGNXIV_OIDC_AUDIENCE=https://<service-host>/github-actions
AGNXIV_ISSUER_PRIVATE_KEY_B64=<base64 private PEM>
AGNXIV_ISSUER_PREVIOUS_PUBLIC_KEYS_B64=<optional old public PEMs>
AGNXIV_MAX_ACTIVE_JOBS_PER_KEY=3
AGNXIV_MAX_JOBS_PER_HOUR=20
AGNXIV_JOB_STALE_MINUTES=45
AGNXIV_MIN_API_KEY_LENGTH=32
AGNXIV_MAX_REQUEST_BYTES=5242880
AGNXIV_ALLOW_DEVELOPMENT_AUTH=false
```

`AGNXIV_GITHUB_WORKFLOW_SHA` is a trust root. Production must also leave
`AGNXIV_ALLOW_DEVELOPMENT_AUTH=false`; development authentication is a
readiness failure and must never be used on an Internet-facing deployment.

 The service rejects callbacks whose GitHub OIDC `workflow_sha` does not exactly match this value. `AGNXIV_GITHUB_REF` must be the matching `refs/tags/...` release ref; the dispatcher converts it to GitHub's tag-name form while callback authentication requires the full OIDC tag ref.

## 4. Apply schema migrations before traffic

Run:

```bash
PYTHONPATH=/app/src python -m agnxiv.service.migrate
```

The migration runner serializes concurrent PostgreSQL upgrades with an advisory
lock. Do not bypass Alembic by creating production tables directly.

## 5. Deploy the digest-pinned service image

Build from `Dockerfile.service`. The base image digest and exact Python
runtime dependency set are part of the attested release manifest.

Do not expose an interactive API console or framework documentation in the
production control plane.

## 6. Require readiness before routing traffic

The deployment is not healthy until all of these succeed:

```bash
curl --fail https://<service-host>/healthz
curl --fail https://<service-host>/readyz
curl --fail https://<service-host>/v1/meta
curl --fail https://<service-host>/v1/issuer
curl --fail https://<service-host>/v1/transparency/head
```

`/readyz` must fail closed for a missing or invalid PostgreSQL connection,
signing key, workflow SHA, or transparency-head integrity failure.

## 7. Run a signed canary verification

Submit one known-safe public paper/repository pair with a fresh
`Idempotency-Key`. Require:

1. the job reaches a terminal state without the stale reaper;
2. the pinned repository commit matches the requested ref;
3. the returned execution has immutable image/source provenance;
4. each decided claim has a DSSE signature;
5. a transparency receipt exists for the job;
6. the receipt chain verifies;
7. the issuer public key verifies the DSSE envelope offline;
8. the job's stored `workflow_run_id`, the GitHub OIDC `run_id`, and the
   signed statement's `predicate.orchestration.workflowRunId` are identical.

Do not use a successful canary to broaden a claim beyond the individual
verification evidence it exercises.

## 8. Enable operational monitoring

Set protected repository variables:

- `AGNXIV_PRODUCTION_URL` — the production HTTPS base URL;
- `AGNXIV_OIDC_AUDIENCE_BASE` — the exact value configured as
  `AGNXIV_OIDC_AUDIENCE` in the service.

The trusted hosted workflow derives both callback URL and per-job OIDC audience
from these protected variables and the job ID. They are deliberately **not**
workflow-dispatch inputs. The scheduled synthetic monitor must then check both
`/healthz` and `/readyz`.

Route workflow failures and SLO alerts to an operator before calling the hosted
service production-grade.

## 9. Backups and restore

Provider backups are not considered proven until a backup has been restored
into a clean database and the full transparency chain verifies after restore.
The repository CI drill validates the procedure; production must perform the
same exercise against the actual provider.

## 10. Rollback

A rollback is a release, not an ad-hoc container restart.

1. select a previously attested release commit;
2. restore that service image/configuration;
3. set `AGNXIV_GITHUB_WORKFLOW_SHA` to the exact commit that contains the
   trusted `hosted-verify.yml` being dispatched;
4. run migrations only if the target schema is forward-compatible;
5. verify readiness, issuer keys, transparency head, and a canary job.

Never weaken OIDC workflow-SHA validation to make a rollback easier.

## Launch declaration

AgnXiv may be called production-grade only when the code gates above are green
**and** the deployment-specific P0 items in `docs/PRODUCTION_READINESS.md`
have concrete evidence.
