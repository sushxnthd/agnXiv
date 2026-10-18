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


def request_github_oidc_token(audience: str) -> str:
    request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not request_url or not request_token:
        raise CallbackError("GitHub Actions OIDC environment is unavailable")

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
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
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
    if not callback_url.startswith("https://"):
        raise CallbackError("callback URL must use HTTPS")

    payload = Path(result_path).read_bytes()
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
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in {200, 201, 204}:
                raise CallbackError(
                    f"callback returned HTTP {response.status}"
                )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[-2000:]
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
