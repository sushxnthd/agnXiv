from __future__ import annotations

import json

import pytest

from agnxiv.service.dispatcher import (
    DispatchError,
    DispatchRequest,
    GitHubActionsDispatcher,
)


class _Response:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._raw if size < 0 else self._raw[:size]


def _dispatcher() -> GitHubActionsDispatcher:
    return GitHubActionsDispatcher(
        token="token",
        repository="sushxnthd/agnXiv",
        ref="refs/tags/agnxiv-v1.0.0",
        workflow="hosted-verify.yml",
    )


def _request() -> DispatchRequest:
    return DispatchRequest(
        job_id="00000000-0000-0000-0000-000000000001",
        mode="auto_verify",
        repository="owner/research",
        repository_ref="a" * 40,
        arxiv_id="2601.00001v1",
        spec_path=None,
    )


def test_dispatch_requires_and_returns_exact_workflow_run_id(monkeypatch) -> None:
    captured: dict = {}

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["version"] = request.get_header("X-github-api-version")
        return _Response(
            {
                "workflow_run_id": 987654321,
                "run_url": "https://api.github.com/repos/x/y/actions/runs/987654321",
                "html_url": "https://github.com/x/y/actions/runs/987654321",
            }
        )

    monkeypatch.setattr(
        "agnxiv.service.dispatcher._NO_REDIRECT_OPENER.open",
        fake_open,
    )

    run_id = _dispatcher().dispatch(_request())

    assert run_id == 987654321
    assert captured["body"]["return_run_details"] is True
    assert captured["body"]["ref"] == "agnxiv-v1.0.0"
    assert captured["body"]["inputs"]["job_id"] == _request().job_id
    assert captured["version"] == "2026-03-10"


@pytest.mark.parametrize(
    "payload",
    [{}, {"workflow_run_id": 0}, {"workflow_run_id": "123"}],
)
def test_dispatch_rejects_missing_or_invalid_run_identity(monkeypatch, payload) -> None:
    monkeypatch.setattr(
        "agnxiv.service.dispatcher._NO_REDIRECT_OPENER.open",
        lambda *args, **kwargs: _Response(payload),
    )
    with pytest.raises(DispatchError, match="valid run ID"):
        _dispatcher().dispatch(_request())


def test_dispatch_rejects_legacy_empty_response(monkeypatch) -> None:
    class _Legacy:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "agnxiv.service.dispatcher._NO_REDIRECT_OPENER.open",
        lambda *args, **kwargs: _Legacy(),
    )
    with pytest.raises(DispatchError, match="did not return run details"):
        _dispatcher().dispatch(_request())
