from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..attestation import canonical_json_sha256
from ..pipeline import VerificationBundle
from ..preprint import parse_arxiv_reference
from ..statement import (
    build_verification_statement,
    public_key_id,
    public_key_pem_from_private,
    sign_statement_ed25519,
)
from ..transparency import GENESIS_HASH, TRANSPARENCY_SCHEMA
from .config import ServiceConfig
from .db import Job, JobStore, TransparencyEntry, job_result
from .dispatcher import DispatchError, DispatchRequest, GitHubActionsDispatcher
from .oidc import GitHubOIDCPolicy, OIDCVerificationError, verify_github_actions_token
from .security import (
    constant_time_equal,
    fingerprint_job_request,
    hash_secret,
    validate_git_ref,
    validate_github_slug,
    validate_idempotency_key,
)

_LOGGER = logging.getLogger("agnxiv.service")


class JobCreate(BaseModel):
    mode: Literal["auto_plan", "auto_verify", "verify_spec"] = "auto_verify"
    repository: str
    repository_ref: str = "main"
    arxiv_id: str | None = None
    spec_path: str | None = None


class WorkerCallback(BaseModel):
    status: Literal["succeeded", "needs_review", "failed"]
    result: dict | None = None
    error: str | None = Field(default=None, max_length=8000)


class TransparencyEntryView(BaseModel):
    sequence: int
    job_id: str
    status: str
    mode: str
    repository: str
    repository_ref: str
    arxiv_id: str | None
    result_sha256: str
    previous_hash: str
    entry_hash: str
    created_at: str


class JobView(BaseModel):
    id: str
    status: str
    mode: str
    repository: str
    repository_ref: str
    arxiv_id: str | None
    spec_path: str | None
    result: dict | None
    error: str | None
    created_at: str
    updated_at: str


def _job_view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        status=job.status,
        mode=job.mode,
        repository=job.repository,
        repository_ref=job.repository_ref,
        arxiv_id=job.arxiv_id,
        spec_path=job.spec_path,
        result=job_result(job),
        error=job.error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _transparency_view(entry: TransparencyEntry) -> TransparencyEntryView:
    return TransparencyEntryView(
        sequence=entry.sequence,
        job_id=entry.job_id,
        status=entry.status,
        mode=entry.mode,
        repository=entry.repository,
        repository_ref=entry.repository_ref,
        arxiv_id=entry.arxiv_id,
        result_sha256=entry.result_sha256,
        previous_hash=entry.previous_hash,
        entry_hash=entry.entry_hash,
        created_at=entry.created_at,
    )


def _validate_worker_result(
    job: Job,
    status: str,
    result: dict | None,
) -> VerificationBundle | None:
    if status == "failed":
        return None

    if not result:
        raise ValueError("successful worker callback requires a result")

    if job.mode in {"auto_plan", "auto_verify"} and result.get("kind") == "auto_plan":
        if result.get("repository_commit") != job.repository_ref:
            raise ValueError("AUTO repository commit does not match pinned job")
        plan = result.get("plan")
        if not isinstance(plan, dict):
            raise ValueError("AUTO result is missing its plan")
        if job.mode == "auto_verify":
            # A plan alone is not scientific verification, even when safe to execute.
            if status != "needs_review":
                raise ValueError("AUTO_VERIFY planning-only result cannot succeed")
        else:
            expected = "succeeded" if plan.get("safe_to_execute") is True else "needs_review"
            if status != expected:
                raise ValueError("AUTO_PLAN status is inconsistent with plan safety")
        return None

    if job.mode not in {"auto_verify", "verify_spec"} or result.get("kind") != "verification":
        raise ValueError("verification job returned the wrong result kind")
    if job.mode == "auto_verify" and result.get("zero_manifest") is not True:
        raise ValueError("AUTO_VERIFY result lacks zero-manifest provenance")
    if job.mode == "verify_spec" and result.get("zero_manifest") is True:
        raise ValueError("VERIFY_SPEC cannot present a zero-manifest result")

    evidence_pairs = [(result.get("discovery"), result.get("bundle"))]
    if job.mode == "auto_verify":
        additional = result.get("additional_verifications", [])
        if not isinstance(additional, list) or len(additional) > 3:
            raise ValueError("invalid additional verification records")
        if not isinstance(result.get("discovery"), dict):
            raise ValueError("AUTO_VERIFY is missing frozen locator provenance")
        for item in additional:
            if not isinstance(item, dict) or not isinstance(item.get("discovery"), dict):
                raise TypeError("additional verification lacks locator provenance")
            evidence_pairs.append((item.get("discovery"), item.get("bundle")))

    bundles = [VerificationBundle.model_validate(raw) for _, raw in evidence_pairs]
    if job.mode == "auto_verify":
        identity = result.get("manuscript_identity")
        if not isinstance(identity, dict):
            raise ValueError("AUTO_VERIFY is missing manuscript identity")
        if not job.arxiv_id:
            raise ValueError("AUTO_VERIFY job is missing its arXiv identity")
        expected_arxiv_id = parse_arxiv_reference(job.arxiv_id).versioned_id
        if identity.get("arxiv_id") != expected_arxiv_id:
            raise ValueError("verification manuscript does not match requested arXiv job")
        manuscript_sha256 = identity.get("sha256")
        if not isinstance(manuscript_sha256, str) or re.fullmatch(
            r"[0-9a-f]{64}", manuscript_sha256
        ) is None:
            raise ValueError("verification manuscript identity lacks canonical SHA-256")
        for (discovery, _), bundle in zip(evidence_pairs, bundles):
            if (
                bundle.manuscript is None
                or bundle.manuscript.sha256 != manuscript_sha256
            ):
                raise ValueError(
                    "verification bundle is not bound to the callback manuscript"
                )
            if discovery.get("claim_id") != bundle.claim.id:
                raise ValueError("frozen locator claim does not match verification bundle")
            if discovery.get("metric") != bundle.claim.metric:
                raise ValueError("frozen locator metric does not match verification bundle")
    expected_authority = (
        "auto_planned" if job.mode == "auto_verify" else "repository_supplied"
    )
    for (discovery, _), bundle in zip(evidence_pairs, bundles):
        if bundle.verification_authority != expected_authority:
            raise ValueError(
                f"{job.mode} result has invalid verification authority"
            )
        if job.mode == "auto_verify":
            expected_evidence = canonical_json_sha256(discovery)
            if bundle.authority_evidence_sha256 != expected_evidence:
                raise ValueError(
                    "AUTO_VERIFY authority is not bound to its frozen locator"
                )
        git = bundle.provenance.git
        if git is None or git.commit != job.repository_ref:
            raise ValueError("verification Git commit does not match pinned job")
        if git.dirty:
            raise ValueError("verification repository is dirty")

    expected = (
        "succeeded"
        if any(
            bundle.record.verdict.value in {"VERIFIED", "CONTRADICTED"}
            for bundle in bundles
        )
        else "needs_review"
    )
    if status != expected:
        raise ValueError("verification status is inconsistent with verdicts")
    return bundles[0]


def _enrich_signed_result(config: ServiceConfig, result: dict | None) -> dict | None:
    if not result or "bundle" not in result or not config.issuer_private_key_b64:
        return result

    bundle = VerificationBundle.model_validate(result["bundle"])
    statement = build_verification_statement(bundle)
    private_key = base64.b64decode(
        config.issuer_private_key_b64,
        validate=True,
    )
    envelope = sign_statement_ed25519(statement, private_key)

    enriched = dict(result)
    enriched["statement"] = statement
    enriched["dsseEnvelope"] = envelope.model_dump(mode="json")

    if result.get("zero_manifest") is True:
        extra_signed = []
        for item in result.get("additional_verifications", []):
            other_bundle = VerificationBundle.model_validate(item["bundle"])
            other_statement = build_verification_statement(other_bundle)
            other_envelope = sign_statement_ed25519(other_statement, private_key)
            extra_signed.append({
                **item,
                "statement": other_statement,
                "dsseEnvelope": other_envelope.model_dump(mode="json"),
            })
        enriched["additional_verifications"] = extra_signed
    return enriched


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    active_config = config or ServiceConfig.from_env()
    store = JobStore(active_config.database_url)

    dispatcher = (
        GitHubActionsDispatcher(
            token=active_config.github_token,
            repository=active_config.github_repository,
            ref=active_config.github_ref,
            workflow=active_config.github_workflow,
        )
        if active_config.github_token
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(
        title="AgnXiv",
        version="1.0.0-beta",
        description="Executable verification for computational research claims.",
        lifespan=lifespan,
    )
    public_host = urlparse(active_config.public_base_url).hostname
    allowed_hosts = [
        host
        for host in (
            public_host,
            "healthcheck.railway.app",
            "localhost",
            "127.0.0.1",
            "testserver",
        )
        if host
    ]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )

    def issuer_keyring() -> tuple[dict, list[dict]]:
        if not active_config.issuer_private_key_b64:
            raise ValueError("issuer private key is not configured")
        private_key = base64.b64decode(
            active_config.issuer_private_key_b64,
            validate=True,
        )
        active_public_pem, active_key_id = public_key_pem_from_private(private_key)
        active = {
            "key_id": active_key_id,
            "algorithm": "Ed25519",
            "public_key_pem": active_public_pem.decode("ascii"),
            "status": "active",
            "signs_new_records": True,
        }
        keys = [active]
        seen = {active_key_id}
        configured_public_keys = (
            (
                "retired",
                True,
                active_config.issuer_previous_public_keys_b64,
            ),
            (
                "revoked",
                False,
                active_config.issuer_revoked_public_keys_b64,
            ),
        )
        for status, trusted, encoded_keys in configured_public_keys:
            for encoded in encoded_keys:
                public_pem = base64.b64decode(encoded, validate=True)
                key_id = public_key_id(public_pem)
                if key_id in seen:
                    raise ValueError("issuer keyring contains a duplicate key")
                seen.add(key_id)
                keys.append(
                    {
                        "key_id": key_id,
                        "algorithm": "Ed25519",
                        "public_key_pem": public_pem.decode("ascii"),
                        "status": status,
                        "trusted_for_historical_records": trusted,
                        "signs_new_records": False,
                    }
                )
        active["trusted_for_historical_records"] = True
        return active, keys

    def issuer_key_valid() -> bool:
        if not active_config.issuer_private_key_b64:
            return False
        try:
            issuer_keyring()
        except (ValueError, binascii.Error, UnicodeDecodeError):
            return False
        return True

    def authenticate(api_key: str | None) -> tuple[str, str]:
        if not active_config.api_keys:
            if api_key not in {None, "", "development"}:
                raise HTTPException(status_code=401, detail="invalid API key")
            value = "development"
            return value, hash_secret(value)

        if not api_key:
            raise HTTPException(status_code=401, detail="missing API key")

        for configured in active_config.api_keys:
            if constant_time_equal(configured, api_key):
                return api_key, hash_secret(api_key)
        raise HTTPException(status_code=401, detail="invalid API key")

    @app.middleware("http")
    async def security_headers(request, call_next):
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if (
                1 <= len(supplied_request_id) <= 64
                and supplied_request_id.isascii()
                and all(
                    char.isalnum() or char in "._-"
                    for char in supplied_request_id
                )
            )
            else uuid.uuid4().hex
        )
        started = time.perf_counter()
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_bytes = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "invalid content-length header"},
                )
            if request_bytes > 5 * 1024 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "request body too large"},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'none'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'"
        )
        if request.url.path == "/" or request.url.path.startswith(("/v1/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        _LOGGER.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                },
                separators=(",", ":"),
            )
        )
        return response

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        database_connected = store.ping()
        issues = list(active_config.production_issues)
        if active_config.issuer_private_key_b64 and not issuer_key_valid():
            issues.append("issuer_key_invalid")
        if not database_connected:
            issues.append("database_unreachable")
        if issues:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not-ready",
                    "issues": sorted(set(issues)),
                    "database": active_config.database_url.split(":", 1)[0],
                },
            )
        return {"status": "ready", "database_connected": True}

    @app.get("/v1/meta")
    def meta() -> dict:
        return {
            "service": "agnxiv",
            "api_version": "v1",
            "verification_modes": ["auto_verify", "auto_plan", "verify_spec"],
            "scientific_contract": "claim-level execution evidence; no paper truth score",
            "zero_manifest": True,
            "signed_statements": bool(active_config.issuer_private_key_b64),
            "transparency_log": True,
            "issuer_key_rollover": True,
        }

    @app.get("/v1/metrics")
    def metrics(
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> dict:
        authenticate(x_api_key)
        store.reap_stale(minutes=active_config.job_stale_minutes)
        return {
            "schema_version": "agnxiv.metrics/1",
            **store.metrics(),
        }

    @app.get("/v1/transparency/head")
    def transparency_head() -> dict:
        sequence, head_hash = store.transparency_head()
        return {
            "schema_version": TRANSPARENCY_SCHEMA,
            "sequence": sequence,
            "head_hash": head_hash,
            "genesis_hash": GENESIS_HASH,
        }

    @app.get("/v1/transparency")
    def transparency_entries(
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict:
        entries = store.list_transparency_entries(
            after_sequence=after,
            limit=limit,
        )
        return {
            "schema_version": TRANSPARENCY_SCHEMA,
            "entries": [
                _transparency_view(entry).model_dump(mode="json")
                for entry in entries
            ],
        }

    @app.get(
        "/v1/transparency/{sequence}",
        response_model=TransparencyEntryView,
    )
    def transparency_entry(sequence: int) -> TransparencyEntryView:
        if sequence < 1:
            raise HTTPException(status_code=404, detail="transparency entry not found")
        entry = store.get_transparency_entry(sequence)
        if entry is None:
            raise HTTPException(status_code=404, detail="transparency entry not found")
        return _transparency_view(entry)

    @app.get("/v1/issuer")
    def issuer() -> dict:
        if not active_config.issuer_private_key_b64:
            raise HTTPException(
                status_code=503,
                detail="hosted issuer key is not configured",
            )
        try:
            active, keys = issuer_keyring()
        except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="hosted issuer keyring is invalid",
            ) from exc
        return {
            "schema_version": "agnxiv.issuer/2",
            "key_id": active["key_id"],
            "algorithm": active["algorithm"],
            "public_key_pem": active["public_key_pem"],
            "keys": keys,
            "rotation_policy": (
                "active key signs new records; retired keys remain trusted "
                "for historical records; revoked keys remain discoverable but "
                "must not be trusted"
            ),
        }

    @app.post("/v1/jobs", response_model=JobView, status_code=202)
    def create_job(
        body: JobCreate,
        x_api_key: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> JobView:
        _, api_hash = authenticate(x_api_key)
        store.reap_stale(minutes=active_config.job_stale_minutes)

        if dispatcher is None:
            raise HTTPException(
                status_code=503,
                detail="hosted execution provider is not configured",
            )

        try:
            repository = validate_github_slug(body.repository)
            repository_ref = validate_git_ref(body.repository_ref)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        arxiv_id = body.arxiv_id
        if body.mode in {"auto_plan", "auto_verify"} and not arxiv_id:
            raise HTTPException(
                status_code=422,
                detail="auto_plan and auto_verify require an arXiv identifier",
            )
        if arxiv_id:
            try:
                arxiv_id = parse_arxiv_reference(arxiv_id).versioned_id
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if body.mode == "verify_spec" and not body.spec_path:
            raise HTTPException(
                status_code=422,
                detail="verify_spec requires spec_path",
            )
        if body.spec_path and (
            body.spec_path.startswith("/")
            or ".." in body.spec_path.split("/")
        ):
            raise HTTPException(status_code=422, detail="unsafe spec_path")

        idempotency_key_hash: str | None = None
        request_fingerprint: str | None = None
        if idempotency_key is not None:
            try:
                normalized_idempotency = validate_idempotency_key(idempotency_key)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            idempotency_key_hash = hash_secret(normalized_idempotency)
            request_fingerprint = fingerprint_job_request(
                mode=body.mode,
                repository=repository,
                repository_ref=repository_ref,
                arxiv_id=arxiv_id,
                spec_path=body.spec_path,
            )
            existing = store.get_by_idempotency(
                api_key_hash=api_hash,
                idempotency_key_hash=idempotency_key_hash,
            )
            if existing is not None:
                if existing.request_fingerprint != request_fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency-Key was already used for a different request",
                    )
                return _job_view(existing)

        if store.count_active(api_hash) >= active_config.max_active_jobs_per_key:
            raise HTTPException(
                status_code=429,
                detail="active job quota exceeded",
            )
        if store.count_recent(api_hash) >= active_config.max_jobs_per_hour:
            raise HTTPException(
                status_code=429,
                detail="hourly job quota exceeded",
            )

        try:
            pinned_ref = dispatcher.resolve_commit(repository, repository_ref)
        except DispatchError as exc:
            raise HTTPException(
                status_code=422,
                detail="repository ref could not be resolved",
            ) from exc

        job_id = str(uuid.uuid4())
        created = True
        if idempotency_key_hash is not None and request_fingerprint is not None:
            job, created = store.create_job_idempotent(
                job_id=job_id,
                api_key_hash=api_hash,
                mode=body.mode,
                repository=repository,
                repository_ref=pinned_ref,
                arxiv_id=arxiv_id,
                spec_path=body.spec_path,
                idempotency_key_hash=idempotency_key_hash,
                request_fingerprint=request_fingerprint,
            )
            if not created:
                if job.request_fingerprint != request_fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency-Key was already used for a different request",
                    )
                return _job_view(job)
        else:
            job = store.create_job(
                job_id=job_id,
                api_key_hash=api_hash,
                mode=body.mode,
                repository=repository,
                repository_ref=pinned_ref,
                arxiv_id=arxiv_id,
                spec_path=body.spec_path,
            )

        request = DispatchRequest(
            job_id=job.id,
            mode=job.mode,
            repository=job.repository,
            repository_ref=job.repository_ref,
            arxiv_id=job.arxiv_id,
            spec_path=job.spec_path,
            callback_url=(
                f"{active_config.public_base_url}/internal/jobs/{job.id}/complete"
            ),
            oidc_audience=active_config.oidc_audience,
        )

        store.mark_running(job.id)
        try:
            dispatcher.dispatch(request)
        except DispatchError as exc:
            store.complete(
                job.id,
                status="failed",
                result=None,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        refreshed = store.get_job(job.id)
        assert refreshed is not None
        return _job_view(refreshed)

    @app.get("/v1/jobs/{job_id}", response_model=JobView)
    def get_job(
        job_id: str,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> JobView:
        _, api_hash = authenticate(x_api_key)
        store.reap_stale(minutes=active_config.job_stale_minutes)
        job = store.get_job(job_id)
        if job is None or job.api_key_hash != api_hash:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_view(job)

    @app.post("/internal/jobs/{job_id}/complete")
    def complete_job(
        job_id: str,
        body: WorkerCallback,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        store.reap_stale(minutes=active_config.job_stale_minutes)
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status not in {"queued", "running"}:
            raise HTTPException(
                status_code=409,
                detail="job is already finalized",
            )
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing GitHub OIDC token")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            verify_github_actions_token(
                token,
                GitHubOIDCPolicy(
                    audience=active_config.oidc_audience,
                    repository=active_config.github_repository,
                    ref=active_config.github_ref,
                    workflow=active_config.github_workflow,
                ),
            )
        except OIDCVerificationError as exc:
            raise HTTPException(status_code=401, detail="untrusted workflow identity") from exc

        try:
            _validate_worker_result(job, body.status, body.result)
            result = _enrich_signed_result(active_config, body.result)
        except (ValueError, TypeError, binascii.Error) as exc:
            store.complete(
                job_id,
                status="failed",
                result=None,
                error=f"result signing/validation failed: {type(exc).__name__}: {exc}",
            )
            raise HTTPException(status_code=422, detail="invalid worker result") from exc

        store.complete(
            job_id,
            status=body.status,
            result=result,
            error=body.error,
        )
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def console() -> str:
        return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgnXiv</title>
<style>
body{font-family:ui-sans-serif,system-ui;max-width:760px;margin:56px auto;padding:0 20px;color:#161616}
h1{font-size:40px;margin-bottom:4px}p{line-height:1.5;color:#555}
label{display:block;margin-top:16px;font-weight:600}
input,select,button{width:100%;box-sizing:border-box;padding:11px;margin-top:6px;border:1px solid #ccc;border-radius:8px;font:inherit}
button{margin-top:22px;background:#111;color:white;border:0;cursor:pointer}
pre{white-space:pre-wrap;background:#f5f5f5;padding:16px;border-radius:8px;min-height:80px}
small{color:#777}
</style>
</head>
<body>
<h1>AgnXiv</h1>
<p>Executable verification for computational research claims.</p>
<label>API key<input id="key" type="password" placeholder="AgnXiv API key"></label>
<label>Mode<select id="mode"><option value="auto_verify">Auto-verify paper</option><option value="auto_plan">Plan only</option><option value="verify_spec">Verify repository manifest</option></select></label>
<label>GitHub repository<input id="repo" placeholder="owner/repository"></label>
<label>Git ref<input id="ref" value="main"></label>
<label>arXiv ID<input id="arxiv" placeholder="1403.6652"></label>
<label>Manifest path<input id="spec" placeholder="agnxiv.json"></label>
<button id="go">Submit</button>
<p><small>Auto-verify executes only safe workflows, and abstains when claim evidence is ambiguous.</small></p>
<pre id="out">Ready.</pre>
<script>
const out=document.getElementById("out");
async function getJob(id,key){
  const r=await fetch("/v1/jobs/"+id,{headers:{"X-API-Key":key}});
  const j=await r.json();out.textContent=JSON.stringify(j,null,2);
  if(["queued","running"].includes(j.status))setTimeout(()=>getJob(id,key),2500);
}
document.getElementById("go").onclick=async()=>{
  const key=document.getElementById("key").value;
  const body={
    mode:document.getElementById("mode").value,
    repository:document.getElementById("repo").value,
    repository_ref:document.getElementById("ref").value,
    arxiv_id:document.getElementById("arxiv").value||null,
    spec_path:document.getElementById("spec").value||null
  };
  out.textContent="Submitting...";
  const r=await fetch("/v1/jobs",{method:"POST",headers:{"Content-Type":"application/json","X-API-Key":key},body:JSON.stringify(body)});
  const j=await r.json();out.textContent=JSON.stringify(j,null,2);
  if(r.ok)getJob(j.id,key);
};
</script>
</body>
</html>"""

    return app


app = create_app()
