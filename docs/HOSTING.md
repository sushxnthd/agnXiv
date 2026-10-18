# Hosted AgnXiv

## Architecture

Hosted AgnXiv separates the trusted service from untrusted research execution.

The control plane contains:

- FastAPI API and browser console;
- PostgreSQL job persistence;
- API-key authentication and per-key active-job quotas;
- fixed GitHub Actions dispatch;
- result validation;
- server-side in-toto and DSSE signing.

The execution plane uses ephemeral GitHub-hosted runners in the initial beta.

The process that downloads and analyzes a paper or repository receives no AgnXiv service credential. It writes a local result file. A later callback process receives a one-time callback token and delivers that result to the control plane.

Scientific commands are still executed through AgnXiv's hardened Docker sandbox with networking disabled and immutable host evidence.

## Why the API container does not execute papers

A public web service should not mount the host Docker socket or run attacker-controlled paper code inside its own application container.

Railway is used only for the web/control plane. The execution-provider interface can later move from GitHub-hosted runners to Firecracker or a dedicated Kubernetes sandbox without changing the public API contract.

## Required production configuration

Set the values shown in .env.example.

A production-ready instance requires:

- PostgreSQL DATABASE_URL;
- one or more long random AGNXIV_API_KEYS;
- HTTPS AGNXIV_PUBLIC_BASE_URL;
- AGNXIV_GITHUB_TOKEN permitted to dispatch workflows in the AgnXiv repository;
- non-default AGNXIV_CALLBACK_SECRET;
- base64-encoded Ed25519 private PEM in AGNXIV_ISSUER_PRIVATE_KEY_B64.

The private issuer key belongs only in the control plane.

## Endpoints

GET /healthz is liveness.

GET /readyz is readiness. It returns HTTP 503 until the production configuration is complete.

POST /v1/jobs submits either:

- auto_plan: repository + exact Git ref + arXiv identifier;
- verify_spec: repository + exact Git ref + path to an AgnXiv manifest.

GET /v1/jobs/{job_id} returns state and result for the submitting API key.

The internal callback route is protected by a job-bound one-time HMAC token.

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

Private manuscripts are intentionally not supported until a confidential execution provider with an appropriate publisher security boundary is deployed.

## Railway deployment

The repository includes:

- Dockerfile.service;
- railway.toml;
- .env.example;
- the service-image CI smoke test.

Create a Railway service from this repository and attach PostgreSQL. Configure the required environment variables. The Railway health check points to /healthz.

The API must be reachable over HTTPS before hosted workers can return results.

## Issuer key

Generate the issuer key offline:

    agnxiv keygen --private-out issuer-private.pem --public-out issuer-public.pem

Base64-encode issuer-private.pem into AGNXIV_ISSUER_PRIVATE_KEY_B64.

Publish issuer-public.pem separately for independent verification of AgnXiv DSSE records.

## Operator principle

The hosted service is allowed to return needs_review.

It is not allowed to silently relax scientific or security requirements to increase the apparent success rate.
