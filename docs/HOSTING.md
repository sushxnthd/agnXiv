# Hosted AgnXiv

## Architecture

Hosted AgnXiv separates the trusted service from untrusted research analysis.

The control plane contains:

- FastAPI API and browser console;
- PostgreSQL job persistence;
- API-key authentication and per-key active-job quotas;
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
- one or more long random AGNXIV_API_KEYS;
- HTTPS AGNXIV_PUBLIC_BASE_URL;
- AGNXIV_GITHUB_TOKEN permitted to dispatch workflows in the AgnXiv repository;
- AGNXIV_OIDC_AUDIENCE bound to the hosted service;
- base64-encoded Ed25519 private PEM in AGNXIV_ISSUER_PRIVATE_KEY_B64.

The private issuer key exists only in the control plane.

## Endpoints

GET /healthz is liveness.

GET /readyz is readiness. It returns HTTP 503 until production configuration is complete.

GET /v1/issuer publishes the Ed25519 public issuer key and key ID.

POST /v1/jobs submits either:

- auto_plan: repository + exact Git ref + arXiv identifier;
- verify_spec: repository + exact Git ref + path to an AgnXiv manifest.

GET /v1/jobs/{job_id} returns state and result for the submitting API key.

The internal completion endpoint accepts only a trusted GitHub Actions OIDC identity.

## AUTO_PLAN semantics

AUTO_PLAN is a planning and triage workflow, not a shortcut to VERIFIED.

It automatically attempts:

1. exact arXiv paper retrieval;
2. quantitative claim extraction;
3. repository evidence mapping;
4. software-environment inference;
5. documented research-command discovery;
6. multi-stage workflow ordering through generated-file dataflow;
7. artifact/input resolution;
8. draft verification-manifest generation.

If the exact environment, workflow, or output locator remains ambiguous, the result is needs_review.

A probabilistic discovery score cannot directly become a scientific verification verdict.

## Current public beta scope

The initial hosted service accepts public GitHub repositories and arXiv papers.

Private manuscripts are intentionally excluded until a confidential execution provider with an appropriate publisher security boundary is deployed.

## Railway deployment

The repository includes Dockerfile.service, railway.toml, .env.example, Alembic migrations, and a service-image smoke test.

Create a Railway service from this repository and attach PostgreSQL. Configure the required environment variables. Railway should build Dockerfile.service and health-check /healthz.

The API must be reachable over HTTPS before hosted workers can return results.

## Issuer key

Generate the issuer key offline:

    agnxiv keygen --private-out issuer-private.pem --public-out issuer-public.pem

Base64-encode issuer-private.pem into AGNXIV_ISSUER_PRIVATE_KEY_B64.

The public key is also exposed through GET /v1/issuer for independent verification.

## Operator principle

The hosted service is allowed to return needs_review.

It is not allowed to silently relax scientific or security requirements to increase the apparent success rate.
