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


def test_untrusted_research_runs_only_on_fresh_github_hosted_vm() -> None:
    text = _read(".github/workflows/hosted-verify.yml")
    execute = text.split("\n  execute:\n", 1)[1].split("\n  callback:\n", 1)[0]
    assert "runs-on: ubuntu-latest" in execute
    assert "runs-on: ubuntu-slim" not in execute
    assert "self-hosted" not in execute
    # The execute job must not be given callback identity or repository-write powers.
    permissions = execute.split("permissions:", 1)[1].split("steps:", 1)[0]
    assert "contents: read" in permissions
    assert "id-token: write" not in permissions
    assert "actions: write" not in permissions


def test_hosted_callback_trust_roots_are_not_dispatch_inputs() -> None:
    text = _read(".github/workflows/hosted-verify.yml")
    input_block = text.split("inputs:", 1)[1].split("\npermissions:", 1)[0]
    assert "callback_url:" not in input_block
    assert "oidc_audience:" not in input_block
    callback = text.split("\n  callback:\n", 1)[1]
    assert "vars.AGNXIV_PRODUCTION_URL" in callback
    assert "vars.AGNXIV_OIDC_AUDIENCE_BASE" in callback
    assert "--callback-url "$CALLBACK_URL"" in callback
    assert "--audience "$OIDC_AUDIENCE"" in callback


def test_pdf_parser_image_is_digest_pinned_and_source_only() -> None:
    dockerfile = _read("Dockerfile.pdf-parser")
    first = dockerfile.splitlines()[0]
    assert "@sha256:" in first
    assert "COPY src ./src" in dockerfile
    assert "COPY constraints-service.txt" in dockerfile
    assert "pypdf==6.21.1" in dockerfile
    assert "pydantic==2.14.1" in dockerfile
    assert "USER 65534:65534" in dockerfile
    assert "pip install -e" not in dockerfile


def test_hosted_workflow_builds_parser_before_untrusted_analysis() -> None:
    workflow = _read(".github/workflows/hosted-verify.yml")
    build = workflow.index("Build trusted no-network manuscript parser")
    execute = workflow.index("Execute untrusted research analysis")
    assert build < execute
    assert "Dockerfile.pdf-parser" in workflow
    assert "agnxiv-pdf-parser:trusted" in workflow


def test_docker_build_context_is_allowlisted() -> None:
    rules = [
        line.strip()
        for line in _read(".dockerignore").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert rules[0] == "**"
    assert "!src/**" in rules
    assert "!migrations/**" in rules
    assert "!constraints-service.txt" in rules
    assert "!Dockerfile.service" in rules
    assert "!Dockerfile.pdf-parser" in rules
    assert all("tests" not in line for line in rules[1:])
    assert all("docs" not in line for line in rules[1:])
