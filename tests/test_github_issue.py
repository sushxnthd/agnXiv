from agnxiv.github_issue import parse_issue_body


def _body(
    *,
    mode: str = "Auto-plan from arXiv + repository",
    repository: str = "phanein/deepwalk",
    ref: str = "main",
    arxiv: str = "1403.6652",
    spec: str = "_No response_",
) -> str:
    return f"""### Mode

{mode}

### Public GitHub repository

{repository}

### Git ref

{ref}

### arXiv ID

{arxiv}

### Verification manifest path

{spec}

### Acknowledgement

- [x] I understand the sandbox boundary.
"""


def test_parse_auto_plan_request() -> None:
    request = parse_issue_body(_body())

    assert request.mode == "auto_plan"
    assert request.repository == "phanein/deepwalk"
    assert request.repository_ref == "main"
    assert request.arxiv_id == "1403.6652"
    assert request.spec_path is None


def test_parse_manifest_request() -> None:
    request = parse_issue_body(
        _body(
            mode="Verify an agnxiv.json manifest",
            repository="owner/research",
            ref="v1.2.0",
            arxiv="_No response_",
            spec="verification/agnxiv.json",
        )
    )

    assert request.mode == "verify_spec"
    assert request.arxiv_id is None
    assert request.spec_path == "verification/agnxiv.json"


def test_reject_manifest_escape() -> None:
    try:
        parse_issue_body(
            _body(
                mode="Verify an agnxiv.json manifest",
                arxiv="_No response_",
                spec="../secret.json",
            )
        )
    except ValueError as exc:
        assert "inside the repository" in str(exc)
    else:
        raise AssertionError("unsafe manifest path was accepted")


def test_reject_non_github_repository() -> None:
    try:
        parse_issue_body(_body(repository="https://evil.example/repo"))
    except ValueError as exc:
        assert "GitHub" in str(exc)
    else:
        raise AssertionError("non-GitHub repository was accepted")

def test_parse_zero_manifest_auto_verify_request() -> None:
    request = parse_issue_body(
        _body(mode="Auto-verify from arXiv + repository")
    )
    assert request.mode == "auto_verify"
    assert request.arxiv_id == "1403.6652"
    assert request.spec_path is None
