from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..pipeline import VerificationBundle
from ..statement import build_verification_statement, sign_statement_ed25519
from .config import ServiceConfig
from .db import Job, JobStore, job_result
from .dispatcher import DispatchError, DispatchRequest, GitHubActionsDispatcher
from .security import constant_time_equal, hash_secret, validate_git_ref, validate_github_slug


class JobCreate(BaseModel):
    mode: Literal["auto_plan", "verify_spec"] = "auto_plan"
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


def _callback_token(secret: str, job_id: str) -> str:
    nonce = secrets.token_urlsafe(24)
    message = f"{job_id}.{nonce}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return f"{nonce}.{signature}"


def _verify_callback_token(secret: str, job_id: str, token: str) -> bool:
    try:
        nonce, supplied = token.rsplit(".", 1)
    except ValueError:
        return False
    message = f"{job_id}.{nonce}".encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


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

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        if not active_config.production_ready:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not-ready",
                    "database": active_config.database_url.split(":", 1)[0],
                    "github_dispatch": bool(active_config.github_token),
                    "api_keys": bool(active_config.api_keys),
                    "issuer_key": bool(active_config.issuer_private_key_b64),
                    "https_public_url": active_config.public_base_url.startswith("https://"),
                },
            )
        return {"status": "ready"}

    @app.post("/v1/jobs", response_model=JobView, status_code=202)
    def create_job(
        body: JobCreate,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> JobView:
        _, api_hash = authenticate(x_api_key)

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

        if body.mode == "auto_plan" and not body.arxiv_id:
            raise HTTPException(
                status_code=422,
                detail="auto_plan requires an arXiv identifier",
            )
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

        if store.count_active(api_hash) >= active_config.max_active_jobs_per_key:
            raise HTTPException(
                status_code=429,
                detail="active job quota exceeded",
            )

        job_id = str(uuid.uuid4())
        callback_token = _callback_token(active_config.callback_secret, job_id)
        job = store.create_job(
            job_id=job_id,
            api_key_hash=api_hash,
            mode=body.mode,
            repository=repository,
            repository_ref=repository_ref,
            arxiv_id=body.arxiv_id,
            spec_path=body.spec_path,
            callback_token_hash=hash_secret(callback_token),
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
            callback_token=callback_token,
        )

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

        store.mark_running(job.id)
        refreshed = store.get_job(job.id)
        assert refreshed is not None
        return _job_view(refreshed)

    @app.get("/v1/jobs/{job_id}", response_model=JobView)
    def get_job(
        job_id: str,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> JobView:
        _, api_hash = authenticate(x_api_key)
        job = store.get_job(job_id)
        if job is None or job.api_key_hash != api_hash:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_view(job)

    @app.post("/internal/jobs/{job_id}/complete")
    def complete_job(
        job_id: str,
        body: WorkerCallback,
        x_agnxiv_callback_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if not x_agnxiv_callback_token:
            raise HTTPException(status_code=401, detail="missing callback token")
        if not _verify_callback_token(
            active_config.callback_secret,
            job_id,
            x_agnxiv_callback_token,
        ):
            raise HTTPException(status_code=401, detail="invalid callback token")
        if not constant_time_equal(
            job.callback_token_hash,
            hash_secret(x_agnxiv_callback_token),
        ):
            raise HTTPException(status_code=401, detail="callback token revoked")

        try:
            result = _enrich_signed_result(active_config, body.result)
        except Exception as exc:
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
    def console(_: Request) -> str:
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
<label>Mode<select id="mode"><option value="auto_plan">Auto-plan paper</option><option value="verify_spec">Verify repository manifest</option></select></label>
<label>GitHub repository<input id="repo" placeholder="owner/repository"></label>
<label>Git ref<input id="ref" value="main"></label>
<label>arXiv ID<input id="arxiv" placeholder="1403.6652"></label>
<label>Manifest path<input id="spec" placeholder="agnxiv.json"></label>
<button id="go">Submit</button>
<p><small>AUTO_PLAN may return needs_review instead of certifying when evidence is ambiguous.</small></p>
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
