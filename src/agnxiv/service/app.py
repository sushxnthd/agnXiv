from __future__ import annotations

import base64
import binascii
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from ..pipeline import VerificationBundle
from ..preprint import parse_arxiv_reference
from ..statement import (
    build_verification_statement,
    public_key_id_from_pem,
    public_key_pem_from_private,
    sign_statement_ed25519,
)
from .config import ServiceConfig
from .db import Job, JobAlreadyFinalized, JobQuotaExceeded, JobStore, job_result
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


class RequestBodyLimitMiddleware:
    """Reject oversized bodies before framework request parsing.

    The middleware buffers at most max_bytes plus one ASGI chunk and then
    replays the exact message sequence to the application. This makes the
    limit independent of Content-Length and Transfer-Encoding semantics.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max(1, max_bytes)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length.decode("ascii"))
            except (ValueError, UnicodeDecodeError):
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "invalid content-length header"},
                )
                await response(scope, receive, send)
                return
            if content_length < 0:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "invalid content-length header"},
                )
                await response(scope, receive, send)
                return
            if content_length > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "request body too large"},
                )
                await response(scope, receive, send)
                return

        messages: list[dict] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "request body too large"},
                    )
                    await response(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


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


def _job_oidc_audience(base_audience: str, job_id: str) -> str:
    return f"{base_audience.rstrip('/')}/jobs/{job_id}"


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


def _is_sha256_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _validate_zero_manifest_binding(
    locator: object,
    bundle: VerificationBundle,
) -> None:
    """Bind worker-discovered locator metadata to the exact executable bundle."""
    if not isinstance(locator, dict):
        raise TypeError("zero-manifest locator must be an object")
    if locator.get("claim_id") != bundle.claim.id:
        raise ValueError("zero-manifest locator claim does not match bundle")
    if locator.get("metric") != (bundle.claim.metric or ""):
        raise ValueError("zero-manifest locator metric does not match bundle")
    regex = locator.get("regex")
    if not isinstance(regex, str) or not regex:
        raise ValueError("zero-manifest locator regex is missing")
    if bundle.observation_method != "explicit_regex":
        raise ValueError("zero-manifest verification must use an explicit regex")
    if bundle.observation_locator != regex:
        raise ValueError("zero-manifest locator regex does not match bundle")
    if not _is_sha256_hex(locator.get("discovery_stdout_sha256")):
        raise ValueError("zero-manifest discovery digest is invalid")
    scale = locator.get("scale")
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
        raise ValueError("zero-manifest observation scale is invalid")

    execution = bundle.execution
    if execution is None or execution.returncode != 0:
        raise ValueError("zero-manifest decision lacks successful execution")
    if not execution.source_unchanged or not execution.artifacts_unchanged:
        raise ValueError("zero-manifest evidence mutated during execution")
    if not execution.image_id.startswith("sha256:"):
        raise ValueError("zero-manifest runtime is not content-addressed")
    if bundle.manuscript is None:
        raise ValueError("zero-manifest bundle is missing manuscript fingerprint")
    if bundle.record.expected != bundle.claim.reported_value:
        raise ValueError("zero-manifest expected value does not match paper claim")

    if bundle.record.verdict.value in {"VERIFIED", "CONTRADICTED"}:
        if len(bundle.record.observations) != 1:
            raise ValueError("zero-manifest decision must contain one observation")
        if bundle.record.observations[0].output_digest != execution.stdout_sha256:
            raise ValueError("zero-manifest observation is not bound to execution output")


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

    raw_bundles = [result.get("bundle")]
    locators: list[object] = []
    if job.mode == "auto_verify":
        additional = result.get("additional_verifications", [])
        if not isinstance(additional, list) or len(additional) > 3:
            raise ValueError("invalid additional verification records")
        locators.append(result.get("discovery"))
        for item in additional:
            if not isinstance(item, dict):
                raise TypeError("additional verification must be an object")
            locators.append(item.get("discovery"))
            raw_bundles.append(item.get("bundle"))

    bundles = [VerificationBundle.model_validate(raw) for raw in raw_bundles]
    for index, bundle in enumerate(bundles):
        git = bundle.provenance.git
        if git is None or git.commit != job.repository_ref:
            raise ValueError("verification Git commit does not match pinned job")
        if git.dirty:
            raise ValueError("verification repository is dirty")
        if job.mode == "auto_verify":
            _validate_zero_manifest_binding(locators[index], bundle)

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

    production_mode = active_config.production_ready
    app = FastAPI(
        title="AgnXiv",
        version="1.0.0-beta",
        description="Executable verification for computational research claims.",
        lifespan=lifespan,
        docs_url=None if production_mode else "/docs",
        redoc_url=None if production_mode else "/redoc",
        openapi_url=None if production_mode else "/openapi.json",
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
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=active_config.max_request_bytes,
    )

    def issuer_keyset() -> dict:
        if not active_config.issuer_private_key_b64:
            raise ValueError("issuer private key is missing")
        private_key = base64.b64decode(
            active_config.issuer_private_key_b64,
            validate=True,
        )
        current_pem, current_id = public_key_pem_from_private(private_key)
        keys = [
            {
                "key_id": current_id,
                "algorithm": "Ed25519",
                "status": "current",
                "public_key_pem": current_pem.decode("ascii"),
            }
        ]
        seen = {current_id}
        for encoded in active_config.issuer_previous_public_keys_b64:
            public_pem = base64.b64decode(encoded, validate=True)
            key_id = public_key_id_from_pem(public_pem)
            if key_id in seen:
                raise ValueError("issuer rollover key identifiers must be unique")
            seen.add(key_id)
            keys.append(
                {
                    "key_id": key_id,
                    "algorithm": "Ed25519",
                    "status": "previous",
                    "public_key_pem": public_pem.decode("ascii"),
                }
            )
        return {
            "schema_version": "agnxiv.issuer-keyset/1",
            "current_key_id": current_id,
            "keys": keys,
        }

    def issuer_key_valid() -> bool:
        if not active_config.issuer_private_key_b64:
            return False
        try:
            issuer_keyset()
        except (ValueError, UnicodeDecodeError, binascii.Error):
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
            (
                "default-src 'none'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'none'"
            )
            if production_mode
            else (
                "default-src 'self'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'none'; "
                "img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self'"
            )
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
        transparency = {"valid": False, "reason": "database_unreachable"}
        if active_config.issuer_private_key_b64 and not issuer_key_valid():
            issues.append("issuer_key_invalid")
        if not database_connected:
            issues.append("database_unreachable")
        else:
            transparency = store.verify_transparency_head()
            if not transparency.get("valid"):
                issues.append("transparency_log_invalid")
        if issues:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not-ready",
                    "issues": sorted(set(issues)),
                    "database": active_config.database_url.split(":", 1)[0],
                    "transparency": transparency,
                },
            )
        return {
            "status": "ready",
            "database_connected": True,
            "transparency": transparency,
        }

    @app.get("/v1/meta")
    def meta() -> dict:
        return {
            "service": "agnxiv",
            "api_version": "v1",
            "verification_modes": ["auto_verify", "auto_plan", "verify_spec"],
            "scientific_contract": "claim-level execution evidence; no paper truth score",
            "zero_manifest": True,
            "signed_statements": bool(active_config.issuer_private_key_b64),
            "issuer_rollover_keys": len(active_config.issuer_previous_public_keys_b64),
            "transparency_log": True,
        }

    @app.get("/v1/transparency/head")
    def transparency_head() -> dict:
        return {
            "schema_version": "agnxiv.transparency-head/1",
            **store.transparency_head(),
        }

    @app.get("/v1/transparency")
    def transparency_page(after: int = 0, limit: int = 100) -> dict:
        if after < 0 or not 1 <= limit <= 500:
            raise HTTPException(
                status_code=422,
                detail="after must be >= 0 and limit must be between 1 and 500",
            )
        return {
            "schema_version": "agnxiv.transparency-page/1",
            "head": store.transparency_head(),
            "entries": store.transparency_entries(after=after, limit=limit),
        }

    @app.get("/v1/transparency/jobs/{job_id}")
    def transparency_job(job_id: str) -> dict:
        receipt = store.transparency_for_job(job_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="transparency receipt not found")
        return receipt

    @app.get("/v1/transparency/verify")
    def transparency_verify(
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> dict:
        authenticate(x_api_key)
        return {
            "schema_version": "agnxiv.transparency-verification/1",
            **store.verify_transparency_chain(),
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

    @app.get("/v1/issuer")
    def issuer() -> dict:
        if not active_config.issuer_private_key_b64:
            raise HTTPException(
                status_code=503,
                detail="hosted issuer key is not configured",
            )
        try:
            keyset = issuer_keyset()
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise HTTPException(
                status_code=503,
                detail="hosted issuer keyset is invalid",
            ) from exc
        current = keyset["keys"][0]
        return {
            **keyset,
            # Backward-compatible aliases for clients that predate key rollover.
            "key_id": current["key_id"],
            "algorithm": current["algorithm"],
            "public_key_pem": current["public_key_pem"],
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
        try:
            job, created = store.create_job_guarded(
                job_id=job_id,
                api_key_hash=api_hash,
                mode=body.mode,
                repository=repository,
                repository_ref=pinned_ref,
                arxiv_id=arxiv_id,
                spec_path=body.spec_path,
                max_active=active_config.max_active_jobs_per_key,
                max_recent=active_config.max_jobs_per_hour,
                idempotency_key_hash=idempotency_key_hash,
                request_fingerprint=request_fingerprint,
            )
        except JobQuotaExceeded as exc:
            detail = (
                "active job quota exceeded"
                if exc.kind == "active"
                else "hourly job quota exceeded"
            )
            raise HTTPException(status_code=429, detail=detail) from exc

        if not created:
            if job.request_fingerprint != request_fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different request",
                )
            return _job_view(job)

        request = DispatchRequest(
            job_id=job.id,
            mode=job.mode,
            repository=job.repository,
            repository_ref=job.repository_ref,
            arxiv_id=job.arxiv_id,
            spec_path=job.spec_path,
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
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing GitHub OIDC token")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            verify_github_actions_token(
                token,
                GitHubOIDCPolicy(
                    audience=_job_oidc_audience(
                        active_config.oidc_audience,
                        job_id,
                    ),
                    repository=active_config.github_repository,
                    ref=active_config.github_ref,
                    workflow=active_config.github_workflow,
                    workflow_sha=active_config.github_workflow_sha,
                ),
            )
        except OIDCVerificationError as exc:
            raise HTTPException(status_code=401, detail="untrusted workflow identity") from exc

        store.reap_stale(minutes=active_config.job_stale_minutes)
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status not in {"queued", "running"}:
            raise HTTPException(
                status_code=409,
                detail="job is already finalized",
            )

        try:
            _validate_worker_result(job, body.status, body.result)
            result = _enrich_signed_result(active_config, body.result)
        except (ValueError, TypeError, binascii.Error) as exc:
            try:
                store.complete(
                    job_id,
                    status="failed",
                    result=None,
                    error=(
                        "result signing/validation failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
            except JobAlreadyFinalized as finalized:
                raise HTTPException(
                    status_code=409,
                    detail="job is already finalized",
                ) from finalized
            raise HTTPException(status_code=422, detail="invalid worker result") from exc

        try:
            store.complete(
                job_id,
                status=body.status,
                result=result,
                error=body.error,
            )
        except JobAlreadyFinalized as exc:
            raise HTTPException(
                status_code=409,
                detail="job is already finalized",
            ) from exc
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def console() -> str:
        if production_mode:
            return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgnXiv Control Plane</title>
</head>
<body>
<h1>AgnXiv control plane</h1>
<p>This endpoint serves the hosted verification API.</p>
<p>The public product is available at https://sushxnthd.github.io/agnXiv/</p>
</body>
</html>"""
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
