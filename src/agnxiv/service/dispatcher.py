from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class DispatchError(RuntimeError):
    """A hosted execution job could not be dispatched."""


@dataclass(frozen=True)
class DispatchRequest:
    job_id: str
    mode: str
    repository: str
    repository_ref: str
    arxiv_id: str | None
    spec_path: str | None
    callback_url: str
    oidc_audience: str


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
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "AgnXiv-Service",
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310 - fixed HTTPS GitHub API origin
                request,
                timeout=20,
            ) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[-2000:]
            raise DispatchError(
                f"could not resolve GitHub ref with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DispatchError(f"could not resolve GitHub ref: {exc}") from exc

        sha = payload.get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise DispatchError("GitHub did not return a full commit SHA")
        return sha

    def dispatch(self, request: DispatchRequest) -> None:
        url = (
            "https://api.github.com/repos/"
            f"{self.repository}/actions/workflows/{self.workflow}/dispatches"
        )
        payload = json.dumps(
            {
                "ref": self.ref,
                "inputs": {
                    "job_id": request.job_id,
                    "mode": request.mode,
                    "repository": request.repository,
                    "repository_ref": request.repository_ref,
                    "arxiv_id": request.arxiv_id or "",
                    "spec_path": request.spec_path or "",
                    "callback_url": request.callback_url,
                    "oidc_audience": request.oidc_audience,
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
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "AgnXiv-Service",
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310 - fixed HTTPS GitHub API origin
                http_request,
                timeout=20,
            ) as response:
                if response.status not in {204, 201, 200}:
                    raise DispatchError(
                        f"GitHub workflow dispatch returned HTTP {response.status}"
                    )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[-2000:]
            raise DispatchError(
                f"GitHub workflow dispatch failed with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DispatchError(f"GitHub workflow dispatch failed: {exc}") from exc
