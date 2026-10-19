_TRUSTED_WORKFLOWS = (
    ".github/workflows/hosted-verify.yml",
    ".github/workflows/verify-request.yml",
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_production_service_does_not_execute_project_build_backend() -> None:
    dockerfile = _read("Dockerfile.service")
    assert "PYTHONPATH=/app/src" in dockerfile
    assert "pip install -e" not in dockerfile
    assert '".[service' not in dockerfile
    assert "COPY pyproject.toml" not in dockerfile
    assert "constraints-service.txt" in dockerfile


def test_trusted_hosted_workflows_do_not_build_agnxiv_package() -> None:
    for path in _TRUSTED_WORKFLOWS:
        text = _read(path)
        assert "pip install -e" not in text, path
        assert "pip install --upgrade pip" not in text, path
        assert "constraints-service.txt" in text, path
        assert "PYTHONPATH:" in text, path


def test_service_constraints_are_exact_pins() -> None:
    lines = [
        line.strip()
        for line in _read("constraints-service.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines
    assert all("==" in line for line in lines)


def test_hosted_callback_runs_even_when_worker_job_fails() -> None:
    text = _read(".github/workflows/hosted-verify.yml")
    callback = text.split("\n  callback:\n", 1)[1]
    assert "if: ${{ always() }}" in callback
    assert "continue-on-error: true" in callback
    assert "Synthesize terminal failure when worker produced no result" in callback
    assert "execute_job=" in callback


def test_release_provenance_is_sigstore_attested_and_binds_trusted_inputs() -> None:
    text = _read(".github/workflows/release-provenance.yml")
    assert "attestations: write" in text
    assert "id-token: write" in text
    assert (
        "actions/attest-build-provenance@"
        "4d101475d8b20a2381f78447822ac1eab6504dd8"
    ) in text
    for required in (
        "commit_sha",
        "service_image_id",
        "service_base_image",
        "dockerfile_sha256",
        "constraints_sha256",
        "hosted_workflow_sha256",
        "production_gate_sha256",
        "migration_files",
    ):
        assert required in text


def test_example_production_config_requires_immutable_workflow_commit() -> None:
    text = _read(".env.example")
    assert "AGNXIV_GITHUB_WORKFLOW_SHA=" in text
    assert "AGNXIV_MAX_REQUEST_BYTES=" in text


def test_transparency_anchor_is_external_sigstore_witness() -> None:
    text = _read(".github/workflows/transparency-anchor.yml")
    assert "schedule:" in text
    assert "AGNXIV_PRODUCTION_URL" in text
    assert "v1/transparency/head" in text
    assert "attestations: write" in text
    assert "id-token: write" in text
    assert (
        "actions/attest-build-provenance@"
        "4d101475d8b20a2381f78447822ac1eab6504dd8"
    ) in text
    assert "gh attestation verify" in text
    assert "--proto '=https'" in text


def test_codeql_security_workflow_is_pinned_and_extended() -> None:
    text = _read(".github/workflows/codeql-security.yml")
    pinned = "6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee"
    assert f"github/codeql-action/init@{pinned}" in text
    assert f"github/codeql-action/analyze@{pinned}" in text
    assert "queries: security-extended" in text
    assert "security-events: write" in text
