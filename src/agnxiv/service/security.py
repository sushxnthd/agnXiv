from __future__ import annotations

from hmac import compare_digest
from hashlib import sha256


_GITHUB_HTTPS_PREFIX = "https://github.com/"


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
        if not candidate.startswith(_GITHUB_HTTPS_PREFIX):
            raise ValueError("only HTTPS GitHub repositories are supported")
        candidate = candidate.removeprefix(_GITHUB_HTTPS_PREFIX)

    candidate = candidate.strip("/").removesuffix(".git")
    parts = candidate.split("/")

    if len(parts) != 2 or not all(_valid_slug_part(part) for part in parts):
        raise ValueError("repository must be a GitHub owner/repository slug")
    return candidate


def validate_git_ref(value: str) -> str:
    ref = value.strip()
    if not ref or len(ref) > 200:
        raise ValueError("invalid Git ref")
    if any(token in ref for token in ("..", "~", "^", ":", "\\", "\n", "\r")):
        raise ValueError("unsafe Git ref")
    return ref
