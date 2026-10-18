from __future__ import annotations

import hashlib
import hmac
import re
from urllib import parse


_GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def validate_github_slug(value: str) -> str:
    candidate = value.strip().removesuffix(".git")
    if candidate.startswith(("http://", "https://")):
        parsed = parse.urlparse(candidate)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise ValueError("only HTTPS GitHub repositories are supported")
        candidate = parsed.path.strip("/").removesuffix(".git")

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
