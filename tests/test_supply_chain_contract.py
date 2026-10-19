from pathlib import Path


_TRUSTED_WORKFLOWS = (
    Path(".github/workflows/hosted-verify.yml"),
    Path(".github/workflows/verify-request.yml"),
)


def test_production_service_does_not_execute_project_build_backend() -> None:
    dockerfile = Path("Dockerfile.service").read_text(encoding="utf-8")
    assert "PYTHONPATH=/app/src" in dockerfile
    assert "pip install -e" not in dockerfile
    assert '".[service' not in dockerfile
    assert "COPY pyproject.toml" not in dockerfile
    assert "constraints-service.txt" in dockerfile


def test_trusted_hosted_workflows_do_not_build_agnxiv_package() -> None:
    for path in _TRUSTED_WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "pip install -e" not in text, path
        assert "pip install --upgrade pip" not in text, path
        assert "constraints-service.txt" in text, path
        assert "PYTHONPATH:" in text, path


def test_service_constraints_are_exact_pins() -> None:
    lines = [
        line.strip()
        for line in Path("constraints-service.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines
    assert all("==" in line for line in lines)
