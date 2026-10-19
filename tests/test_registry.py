from __future__ import annotations

import pytest

from agnxiv.registry import (
    RegistryLookupError,
    normalize_doi,
    publication_binding_from_crossref_payload,
    publication_binding_from_datacite_payload,
)


def test_doi_normalization_accepts_canonical_prefix_variants() -> None:
    expected = "10.1145/1234.5678"
    assert normalize_doi(expected) == expected
    assert normalize_doi("DOI:10.1145/1234.5678") == expected
    assert normalize_doi("https://doi.org/10.1145/1234.5678") == expected


@pytest.mark.parametrize(
    "value",
    ["", "not-a-doi", "10.12/x", "https://evil.example/10.1145/1234.5678"],
)
def test_invalid_doi_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="invalid DOI"):
        normalize_doi(value)


def test_crossref_binding_is_content_bound() -> None:
    payload = {
        "status": "ok",
        "message": {
            "DOI": "10.1145/1234.5678",
            "title": ["A reproducible result"],
            "publisher": "Example Publisher",
            "type": "journal-article",
            "URL": "https://doi.org/10.1145/1234.5678",
            "published-online": {"date-parts": [[2026, 10, 1]]},
            "member": "123",
        },
    }
    binding = publication_binding_from_crossref_payload(
        "https://doi.org/10.1145/1234.5678",
        payload,
        retrieved_at="2026-10-19T00:00:00Z",
    )
    assert binding.registry == "crossref"
    assert binding.doi == "10.1145/1234.5678"
    assert binding.publisher == "Example Publisher"
    assert binding.published == "2026-10-01"
    assert len(binding.registry_record_sha256) == 64


def test_crossref_wrong_doi_is_rejected() -> None:
    payload = {"message": {"DOI": "10.9999/wrong"}}
    with pytest.raises(RegistryLookupError, match="different DOI"):
        publication_binding_from_crossref_payload("10.1145/1234.5678", payload)


def test_datacite_binding_is_content_bound() -> None:
    payload = {
        "data": {
            "attributes": {
                "doi": "10.5281/zenodo.1234567",
                "titles": [{"title": "Archived verification dataset"}],
                "publisher": {"name": "Zenodo"},
                "types": {"resourceTypeGeneral": "Dataset"},
                "published": "2026",
                "url": "https://zenodo.org/records/1234567",
            }
        }
    }
    binding = publication_binding_from_datacite_payload(
        "10.5281/zenodo.1234567",
        payload,
        retrieved_at="2026-10-19T00:00:00Z",
    )
    assert binding.registry == "datacite"
    assert binding.doi == "10.5281/zenodo.1234567"
    assert binding.publisher == "Zenodo"
    assert binding.work_type == "Dataset"
    assert len(binding.registry_record_sha256) == 64
