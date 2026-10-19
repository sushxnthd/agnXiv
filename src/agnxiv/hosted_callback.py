from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class CallbackError(RuntimeError):
    """A hosted result callback could not be delivered."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "redirects are not allowed for authenticated callbacks",
            headers,
            fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


_MAX_OIDC_RESPONSE_BYTES = 64 * 1024
_MAX_CALLBACK_PAYLOAD_BYTES = 5 * 1024 * 1024


def _validated_https_url(
    value: str,
    *,
    required_host_suffix: str | None = None,
) -> str:
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise CallbackError("URL must be credential-free HTTPS")
    if required_host_suffix is not None:
        host = parsed.hostname.lower().rstrip(".")
        suffix = required_host_suffix.lower().lstrip(".")
        if host != suffix and not host.endswith("." + suffix):
            raise CallbackError("URL host is outside the trusted GitHub Actions origin")
    return value


def request_github_oidc_token(audience: str) -> str:
    request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not request_url or not request_token:
        raise CallbackError("GitHub Actions OIDC environment is unavailable")
    request_url = _validated_https_url(
        request_url,
        required_host_suffix="actions.githubusercontent.com",
    )

    separator = "&" if "?" in request_url else "?"
    url = request_url + separator + urllib.parse.urlencode({"audience": audience})
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {request_token}",
            "User-Agent": "AgnXiv-Hosted-Callback",
        },
    )

    try:
        with _NO_REDIRECT_OPENER.open(
            request,
            timeout=20,
        ) as response:
            raw = response.read(_MAX_OIDC_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_OIDC_RESPONSE_BYTES:
                raise CallbackError("GitHub OIDC response exceeded size limit")
            payload = json.loads(raw)
    except urllib.error.URLError as exc:
        raise CallbackError(f"could not obtain GitHub OIDC token: {exc}") from exc

    token = payload.get("value")
    if not isinstance(token, str) or not token:
        raise CallbackError("GitHub OIDC response did not contain a token")
    return token


def send_result(
    *,
    result_path: str | Path,
    callback_url: str,
    oidc_token: str,
) -> None:
    callback_url = _validated_https_url(callback_url)

    result = Path(result_path)
    if not result.is_file() or result.is_symlink():
        raise CallbackError("callback result must be a regular file")
    if result.stat().st_size > _MAX_CALLBACK_PAYLOAD_BYTES:
        raise CallbackError("callback result exceeds payload size limit")
    payload = result.read_bytes()
    request = urllib.request.Request(
        callback_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {oidc_token}",
            "User-Agent": "AgnXiv-Hosted-Callback",
        },
    )

    try:
        with _NO_REDIRECT_OPENER.open(
            request,
            timeout=30,
        ) as response:
            if response.status not in {200, 201, 204}:
                raise CallbackError(
                    f"callback returned HTTP {response.status}"
                )
    except urllib.error.HTTPError as exc:
        body = exc.read(2000).decode("utf-8", errors="replace")
        raise CallbackError(
            f"callback failed with HTTP {exc.code}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise CallbackError(f"callback delivery failed: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--callback-url", required=True)
    parser.add_argument("--audience", required=True)
    args = parser.parse_args()

    send_result(
        result_path=args.result,
        callback_url=args.callback_url,
        oidc_token=request_github_oidc_token(args.audience),
    )


if __name__ == "__main__":
    main()
