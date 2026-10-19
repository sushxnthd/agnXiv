from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

TRANSPARENCY_SCHEMA = "agnxiv.transparency/1"
GENESIS_HASH = "0" * 64


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON deterministically for durable transparency hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def entry_body(
    *,
    sequence: int,
    job_id: str,
    status: str,
    mode: str,
    repository: str,
    repository_ref: str,
    arxiv_id: str | None,
    result_sha256: str,
    previous_hash: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": TRANSPARENCY_SCHEMA,
        "sequence": sequence,
        "job_id": job_id,
        "status": status,
        "mode": mode,
        "repository": repository,
        "repository_ref": repository_ref,
        "arxiv_id": arxiv_id,
        "result_sha256": result_sha256,
        "previous_hash": previous_hash,
        "created_at": created_at,
    }


def compute_entry_hash(**kwargs: Any) -> str:
    return sha256(canonical_json_bytes(entry_body(**kwargs))).hexdigest()
