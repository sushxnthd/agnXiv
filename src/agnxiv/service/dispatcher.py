from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class DispatchError(RuntimeError):
    """A hosted execution job could not be dispatched."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "redirects are not allowed for authenticated GitHub API requests",
            headers,
            fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())
_MAX_GITHUB_RESPONSE_BYTES = 64 * 1024


def _read_json_response(response) -> dict:
    raw = response.read(_MAX_GITHUB_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_GITHUB_RESPONSE_BYTES:
        raise DispatchError("GitHub API response is too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DispatchError("GitHub API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DispatchError("GitHub API returned an invalid response schema")
    return payload


def workflow_dispatch_ref(ref: str) -> str:
    """Convert a full Git ref into the branch/tag name required by GitHub."""
    for prefix in ("refs/heads/", "refs/tags/"):
        if ref.startswith(prefix):
            return ref.removeprefix(prefix)
    return ref


@dataclass(frozen=True)
class DispatchRequest:
    job_id: str
    mode: str
    repository: str
    repository_ref: str
    arxiv_id: str | None
    spec_path: str | None


class GitHubActionsDispatcher:
    def __init__(
        self,
        *,
        token: str,
        repository: str,
        ref: str,
        workflow: str,
    ) -> None:
        self.token = token
        self.repository = repository
        self.ref = ref
        self.workflow = workflow


    def resolve_commit(self, repository: str, ref: str) -> str:
        encoded_ref = urllib.parse.quote(ref, safe="")
        url = (
            "https://api.github.com/repos/"
            + repository
            + "/commits/"
            + encoded_ref
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "AgnXiv-Service",
            },
        )
        try:
            with _NO_REDIRECT_OPENER.open(  # nosec B310 - HTTPS origin validated above
                request,
                timeout=20,
            ) as response:
                payload = _read_json_response(response)
        except urllib.error.HTTPError as exc:
            body = (
            exc.read(2000).decode("utf-8", errors="replace")
            if exc.fp is not None
            else ""
        )
            raise DispatchError(
                f"could not resolve GitHub ref with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DispatchError(f"could not resolve GitHub ref: {exc}") from exc

        sha = payload.get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise DispatchError("GitHub did not return a full commit SHA")
        return sha

    def dispatch(self, request: DispatchRequest) -> int:
        url = (
            "https://api.github.com/repos/"
            f"{self.repository}/actions/workflows/{self.workflow}/dispatches"
        )
        payload = json.dumps(
            {
                "ref": workflow_dispatch_ref(self.ref),
                "return_run_details": True,
                "inputs": {
                    "job_id": request.job_id,
                    "mode": request.mode,
                    "repository": request.repository,
                    "repository_ref": request.repository_ref,
                    "arxiv_id": request.arxiv_id or "",
                    "spec_path": request.spec_path or "",
                },
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "Content-Type": "application/json",
                "User-Agent": "AgnXiv-Service",
            },
        )
        try:
            with _NO_REDIRECT_OPENER.open(  # nosec B310 - HTTPS origin validated above
                http_request,
                timeout=20,
            ) as response:
                if response.status != 200:
                    raise DispatchError(
                        "GitHub workflow dispatch did not return run details "
                        f"(HTTP {response.status})"
                    )
                details = _read_json_response(response)
        except urllib.error.HTTPError as exc:
            body = (
            exc.read(2000).decode("utf-8", errors="replace")
            if exc.fp is not None
            else ""
        )
            raise DispatchError(
                f"GitHub workflow dispatch failed with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DispatchError(f"GitHub workflow dispatch failed: {exc}") from exc
        run_id = details.get("workflow_run_id") if isinstance(details, dict) else None
        if not isinstance(run_id, int) or run_id <= 0:
            raise DispatchError("GitHub workflow dispatch did not return a valid run ID")
        return run_id
