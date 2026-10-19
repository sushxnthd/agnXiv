from __future__ import annotations

import argparse
import json
from pathlib import Path

from .claims import extract_claims_from_pdf

_MAX_PAGES = 300
_MAX_TEXT_CHARS = 5_000_000
_MAX_CLAIMS = 2_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    try:
        claims = extract_claims_from_pdf(
            args.input,
            max_pages=_MAX_PAGES,
            max_text_chars=_MAX_TEXT_CHARS,
        )
        if len(claims) > _MAX_CLAIMS:
            raise RuntimeError(
                f"PDF produced {len(claims)} claims; hosted limit is {_MAX_CLAIMS}"
            )
        payload = {
            "ok": True,
            "claims": [claim.model_dump(mode="json") for claim in claims],
        }
        status = 0
    except Exception as exc:  # noqa: BLE001 - isolated parser crash boundary
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
        }
        status = 2

    output.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
