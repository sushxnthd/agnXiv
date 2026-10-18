from __future__ import annotations

import hashlib
import hmac
import re


_GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_HTTPS_PREFIX = "https://github.com/"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def validate_github_slug(value: str) -> str:
    candidate = value.strip()

    if candidate.startswith("http://"):
        raise ValueError("only HTTPS GitHub repositories are supported")

    if candidate.startswith("https://"):
        if not candidate.startswith(_GITHUB_HTTPS_PREFIX):
            raise ValueError("only HTTPS GitHub repositories are supported")
        candidate = candidate.removeprefix(_GITHUB_HTTPS_PREFIX)

    candidate = candidate.strip("/").removesuffix(".git")

    if not _GITHUB_SLUG_RE.fullmatch(candidate):
        raise ValueError("repository must be a GitHub owner/repository slug")
    return candidate


def validate_git_ref(value: str) -> str:
    ref = value.strip()
    if not ref or len(ref) > 200:
        raise ValueError("invalid Git ref")
    if any(token in ref for token in ("..", "~", "^", ":", "\\", "\n", "\r")):
        raise ValueError("unsafe Git ref")
    return ref
