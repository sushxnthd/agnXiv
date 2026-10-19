from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from pydantic import BaseModel

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", flags=re.IGNORECASE)


class RegistryLookupError(RuntimeError):
    """A publication identifier could not be resolved conservatively."""


class PublicationBinding(BaseModel):
    schema_version: str = "agnxiv.publication/1"
    registry: str = "crossref"
    doi: str
    title: str | None = None
    publisher: str | None = None
    work_type: str | None = None
    published: str | None = None
    canonical_url: str | None = None
    member: str | None = None
    retrieved_at: str
    registry_record_sha256: str


def normalize_doi(value: str) -> str:
    candidate = urllib.parse.unquote(value.strip())
    lowered = candidate.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix):].strip()
            break
    if not candidate or len(candidate) > 255:
        raise ValueError("invalid DOI")
    if any(char.isspace() or ord(char) < 32 for char in candidate):
        raise ValueError("invalid DOI")
    if not _DOI_RE.fullmatch(candidate):
        raise ValueError("invalid DOI")
    return candidate.lower()


def _published_date(message: dict) -> str | None:
    for key in ("published-print", "published-online", "published", "issued"):
        value = message.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        date = parts[0]
        if not date:
            continue
        year = int(date[0])
        month = int(date[1]) if len(date) > 1 else 1
        day = int(date[2]) if len(date) > 2 else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def publication_binding_from_crossref_payload(
    requested_doi: str,
    payload: dict,
    *,
    retrieved_at: str | None = None,
) -> PublicationBinding:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise RegistryLookupError("Crossref response is missing a work record")
    returned = message.get("DOI")
    if not isinstance(returned, str):
        raise RegistryLookupError("Crossref work record is missing DOI")
    normalized = normalize_doi(requested_doi)
    if normalize_doi(returned) != normalized:
        raise RegistryLookupError("Crossref returned a different DOI")

    titles = message.get("title")
    title = titles[0].strip() if isinstance(titles, list) and titles and isinstance(titles[0], str) else None
    publisher = message.get("publisher") if isinstance(message.get("publisher"), str) else None
    canonical_url = message.get("URL") if isinstance(message.get("URL"), str) else None
    work_type = message.get("type") if isinstance(message.get("type"), str) else None
    member = message.get("member") if isinstance(message.get("member"), str) else None

    canonical = json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    from hashlib import sha256

    return PublicationBinding(
        doi=normalized,
        title=title,
        publisher=publisher,
        work_type=work_type,
        published=_published_date(message),
        canonical_url=canonical_url,
        member=member,
        retrieved_at=retrieved_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        registry_record_sha256=sha256(canonical.encode("utf-8")).hexdigest(),
    )


def resolve_crossref_doi(doi: str, *, timeout: int = 15) -> PublicationBinding:
    normalized = normalize_doi(doi)
    encoded = urllib.parse.quote(normalized, safe="")
    request = urllib.request.Request(
        f"https://api.crossref.org/works/{encoded}",
        headers={
            "Accept": "application/json",
            "User-Agent": "AgnXiv/1.0 (publication-registry-verification)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RegistryLookupError("DOI is not present in Crossref") from exc
        raise RegistryLookupError(f"Crossref lookup failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RegistryLookupError("Crossref lookup could not be completed") from exc
    return publication_binding_from_crossref_payload(normalized, payload)
