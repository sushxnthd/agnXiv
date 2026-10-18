from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from pathlib import Path


class CallbackError(RuntimeError):
    """A hosted result callback could not be delivered."""


def send_result(
    *,
    result_path: str | Path,
    callback_url: str,
    callback_token: str,
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
            "X-AgnXiv-Callback-Token": callback_token,
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
    parser.add_argument("--callback-token", required=True)
    args = parser.parse_args()

    send_result(
        result_path=args.result,
        callback_url=args.callback_url,
        callback_token=args.callback_token,
    )


if __name__ == "__main__":
    main()
