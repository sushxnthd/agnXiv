from __future__ import annotations

import re

from pydantic import BaseModel, Field

_ARXIV_RE = re.compile(
    r"^(?:arXiv:)?(?P<identifier>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))"
    r"(?:v(?P<version>\d+))?$",
    flags=re.IGNORECASE,
)


class ArxivReference(BaseModel):
    identifier: str
    version: int | None = Field(default=None, ge=1)

    @property
    def versioned_id(self) -> str:
        suffix = f"v{self.version}" if self.version is not None else ""
        return f"{self.identifier}{suffix}"

    @property
    def abstract_url(self) -> str:
        return f"https://arxiv.org/abs/{self.versioned_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.versioned_id}"


def parse_arxiv_reference(value: str) -> ArxivReference:
    """Parse modern or legacy arXiv identifiers while preserving the version."""
    cleaned = value.strip()
    for prefix in ("https://arxiv.org/abs/", "https://arxiv.org/pdf/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    if cleaned.endswith(".pdf"):
        cleaned = cleaned[:-4]

    match = _ARXIV_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(f"not a recognized arXiv identifier: {value}")

    version = match.group("version")
    return ArxivReference(
        identifier=match.group("identifier"),
        version=int(version) if version else None,
    )
