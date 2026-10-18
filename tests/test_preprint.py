import pytest

from agnxiv.preprint import parse_arxiv_reference


def test_parses_versioned_arxiv_identifier() -> None:
    ref = parse_arxiv_reference("arXiv:2610.12345v3")
    assert ref.identifier == "2610.12345"
    assert ref.version == 3
    assert ref.versioned_id == "2610.12345v3"


def test_parses_arxiv_pdf_url() -> None:
    ref = parse_arxiv_reference("https://arxiv.org/pdf/2610.12345v2.pdf")
    assert ref.version == 2
    assert ref.abstract_url.endswith("2610.12345v2")


def test_rejects_non_arxiv_identifier() -> None:
    with pytest.raises(ValueError):
        parse_arxiv_reference("not-a-paper")
