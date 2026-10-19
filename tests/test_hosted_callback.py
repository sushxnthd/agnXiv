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
