from __future__ import annotations

import re
from hashlib import sha256
from hmac import compare_digest
from urllib.parse import urlparse

_GITHUB_HTTPS_PREFIX = "https://github.com/"
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def hash_secret(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return compare_digest(left.encode(), right.encode())


def _valid_slug_part(value: str) -> bool:
    return bool(value) and value.isascii() and all(
        character.isalnum() or character in "_.-"
        for character in value
    )


def validate_github_slug(value: str) -> str:
    candidate = value.strip()

    if candidate.startswith("http://"):
        raise ValueError("only HTTPS GitHub repositories are supported")

    if candidate.startswith("https://"):
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise ValueError("only HTTPS GitHub repositories are supported")
        if parsed.query or parsed.fragment or parsed.params:
            raise ValueError("repository URL may not contain query or fragment data")
        candidate = parsed.path.strip("/")

    candidate = candidate.strip("/").removesuffix(".git")
    parts = candidate.split("/")

    if len(parts) != 2 or not all(_valid_slug_part(part) for part in parts):
        raise ValueError("repository must be a GitHub owner/repository slug")
    return candidate


def validate_git_ref(value: str) -> str:
    ref = value.strip()
    if not ref or len(ref) > 200:
        raise ValueError("invalid Git ref")
    if ref.startswith("-") or not _REF_RE.fullmatch(ref):
        raise ValueError("unsafe Git ref")
    if any(token in ref for token in ("..", "//", "@{")):
        raise ValueError("unsafe Git ref")
    if ref.endswith(("/", ".", ".lock")):
        raise ValueError("unsafe Git ref")
    return ref
