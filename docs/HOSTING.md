# Hosted AgnXiv

## Architecture

Hosted AgnXiv separates the trusted service from untrusted research analysis.

The control plane contains:

- FastAPI API and browser console;
- PostgreSQL job persistence;
- API-key authentication with active-job and hourly quotas;
- fixed GitHub Actions dispatch;
- strict GitHub Actions OIDC verification;
- result validation;
- server-side in-toto and DSSE signing.

The initial execution plane uses ephemeral GitHub-hosted runners.

## Credential boundary

The hosted-verify workflow uses two fresh jobs.

The execute job:

- has contents:read only;
- disables persisted checkout credentials;
- receives no AgnXiv API key, database credential, issuer key, service secret, or OIDC permission;
- clones only the requested public GitHub repository;
- downloads the requested arXiv PDF for AUTO_PLAN;
- performs planning or isolated Docker verification;
- uploads one JSON result artifact.

The callback job:

- runs on a fresh VM;
- downloads only the JSON result;
- has id-token:write;
- obtains a short-lived GitHub OIDC token for the configured AgnXiv audience;
- posts the JSON result to the control plane.

The control plane verifies the OIDC signature and requires the configured repository, branch, hosted-verify workflow, workflow_dispatch event, GitHub-hosted runner, and audience before accepting a result.

## Why the API container does not execute papers

A public web service should not mount a host Docker socket or execute paper code inside its control-plane container.

Railway hosts only the API/control plane. The execution-provider interface can later move from GitHub-hosted runners to Firecracker or a dedicated Kubernetes sandbox without changing the public API contract.

## Required production configuration

Set the values shown in .env.example.

A production-ready instance requires:

- PostgreSQL DATABASE_URL;
- one or more random AGNXIV_API_KEYS meeting AGNXIV_MIN_API_KEY_LENGTH (32 by default);
- HTTPS AGNXIV_PUBLIC_BASE_URL;
- AGNXIV_GITHUB_TOKEN permitted to dispatch workflows in the AgnXiv repository;
- AGNXIV_OIDC_AUDIENCE bound to the hosted service;
- base64-encoded Ed25519 private PEM in AGNXIV_ISSUER_PRIVATE_KEY_B64.

The private issuer key exists only in the control plane.

## Endpoints

GET /healthz is liveness.

GET /readyz is readiness. It returns HTTP 503 until production configuration is complete.

GET /v1/meta publishes the supported verification modes and service contract without secrets.

GET /v1/metrics returns authenticated, secret-free job counters for operators.

GET /v1/issuer publishes the Ed25519 public issuer key and key ID.

Every submitted repository ref is resolved to an exact 40-character Git commit before dispatch. Returned evidence must match that pinned commit.

POST /v1/jobs submits:

- auto_verify: repository + Git ref + arXiv identifier; execute only when safety-critical planning stages are resolved;
- auto_plan: repository + Git ref + arXiv identifier; planning/triage only;
- verify_spec: repository + Git ref + path to an AgnXiv manifest.

Clients should send an Idempotency-Key header for POST /v1/jobs. The service binds that key to a canonical request fingerprint. Retries return the existing job; reusing the same key for different inputs returns HTTP 409. The database also enforces per-API-key idempotency uniqueness to close concurrent retry races.

GET /v1/jobs/{job_id} returns state and result for the submitting API key. Queued/running jobs whose callback never arrives are failed after AGNXIV_JOB_STALE_MINUTES, preventing permanent quota exhaustion.

The internal completion endpoint accepts only a trusted GitHub Actions OIDC identity.

## AUTO_VERIFY and AUTO_PLAN semantics

AUTO_VERIFY extends the conservative planner with answer-blind locator freezing and isolated execution. AUTO_PLAN remains planning and triage only; neither mode may turn a discovery score directly into VERIFIED.

The automatic planner attempts:

1. exact arXiv paper retrieval;
2. quantitative claim extraction;
3. repository evidence mapping;
4. software-environment inference;
5. documented research-command discovery;
6. multi-stage workflow ordering through generated-file dataflow;
7. artifact/input resolution;
8. draft verification-manifest generation.

If the exact environment, workflow, or output locator remains ambiguous, the result is needs_review.

When AUTO_VERIFY reaches execution, the raw numeric verifier verdict is preserved separately from evidence strength. Floating or otherwise weakly reconstructed dependency environments are labeled CONDITIONAL evidence; they are not presented as publication-era equivalence.

A probabilistic discovery score cannot directly become a scientific verification verdict.

## Current public beta scope

The initial hosted service accepts public GitHub repositories and arXiv papers.

Private manuscripts are intentionally excluded until a confidential execution provider with an appropriate publisher security boundary is deployed.

## Railway deployment

The repository includes Dockerfile.service, railway.toml, .env.example, Alembic migrations, and a service-image smoke test.

Create a Railway service from this repository and attach PostgreSQL. Configure the required environment variables. Railway should build Dockerfile.service and health-check /readyz so a deployment cannot become active until its production configuration and database are ready.

The API must be reachable over HTTPS before hosted workers can return results.

## Issuer key

Generate the issuer key offline:

    agnxiv keygen --private-out issuer-private.pem --public-out issuer-public.pem

Base64-encode issuer-private.pem into AGNXIV_ISSUER_PRIVATE_KEY_B64.

The public key is also exposed through GET /v1/issuer for independent verification.

## Operator principle

The hosted service is allowed to return needs_review.

It is not allowed to silently relax scientific or security requirements to increase the apparent success rate.


## Operational hardening

- Requests receive an X-Request-ID correlation identifier. A safe client-supplied ID is echoed; unsafe values are replaced.
- Hosted job metrics are available only after API-key authentication.
- GitHub Actions used in trusted workflows are pinned to immutable commit SHAs.
- The service container does not trust arbitrary X-Forwarded-* headers.
- Readiness validates database type/connectivity, HTTPS configuration, API-key strength, GitHub dispatch configuration, and issuer-key parseability.
