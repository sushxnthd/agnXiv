from __future__ import annotations

import json
from pathlib import Path

import pytest

from agnxiv.hosted_callback import (
    CallbackError,
    _validated_https_url,
    request_github_oidc_token,
    send_result,
)


def test_https_url_validator_rejects_credentials_fragments_and_non_https() -> None:
    for value in (
        "http://agnxiv.example/callback",
        "file:///etc/passwd",
        "https://user:pass@agnxiv.example/callback",
        "https://agnxiv.example/callback#fragment",
    ):
        with pytest.raises(CallbackError):
            _validated_https_url(value)


def test_oidc_request_url_must_stay_on_github_actions_origin(monkeypatch) -> None:
    monkeypatch.setenv(
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "https://attacker.example/token",
    )
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "secret")
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network access must not happen")

    monkeypatch.setattr("agnxiv.hosted_callback.urllib.request.urlopen", forbidden)
    with pytest.raises(CallbackError, match="trusted GitHub Actions origin"):
        request_github_oidc_token("https://agnxiv.example/jobs/1")
    assert called is False


def test_callback_rejects_credentialed_https_before_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps({"status": "failed", "result": None, "error": "test"}),
        encoding="utf-8",
    )
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network access must not happen")

    monkeypatch.setattr("agnxiv.hosted_callback.urllib.request.urlopen", forbidden)
    with pytest.raises(CallbackError, match="credential-free HTTPS"):
        send_result(
            result_path=result,
            callback_url="https://user:pass@agnxiv.example/internal/jobs/x/complete",
            oidc_token="token",
        )
    assert called is False


class _FakeResponse:
    def __init__(self, payload: bytes = b"", status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


def test_oidc_response_size_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv(
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "https://token.actions.githubusercontent.com/token",
    )
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "secret")
    monkeypatch.setattr(
        "agnxiv.hosted_callback._NO_REDIRECT_OPENER.open",
        lambda *args, **kwargs: _FakeResponse(b"x" * (64 * 1024 + 1)),
    )

    with pytest.raises(CallbackError, match="size limit"):
        request_github_oidc_token("https://agnxiv.example/jobs/1")


def test_callback_result_size_is_bounded_before_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = tmp_path / "result.json"
    result.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network access must not happen")

    monkeypatch.setattr(
        "agnxiv.hosted_callback._NO_REDIRECT_OPENER.open",
        forbidden,
    )
    with pytest.raises(CallbackError, match="payload size limit"):
        send_result(
            result_path=result,
            callback_url="https://agnxiv.example/internal/jobs/x/complete",
            oidc_token="token",
        )
    assert called is False


def test_callback_redirect_is_rejected_without_following_location(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import urllib.error
    import urllib.request

    result = tmp_path / "result.json"
    result.write_text(
        json.dumps({"status": "failed", "result": None, "error": "test"}),
        encoding="utf-8",
    )
    calls = 0

    def redirect_once(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            request.full_url,
            302,
            "Found",
            {"Location": "https://attacker.example/collect"},
            None,
        )

    monkeypatch.setattr(
        "agnxiv.hosted_callback._NO_REDIRECT_OPENER.open",
        redirect_once,
    )
    with pytest.raises(CallbackError, match="HTTP 302"):
        send_result(
            result_path=result,
            callback_url="https://agnxiv.example/internal/jobs/x/complete",
            oidc_token="secret-token",
        )
    assert calls == 1
