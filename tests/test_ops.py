from pathlib import Path

from fastapi.testclient import TestClient

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.ops import OperationalSLOPolicy, evaluate_operational_status


def _config(database_url: str) -> ServiceConfig:
    return ServiceConfig(
        database_url=database_url,
        api_keys=("k" * 48,),
        public_base_url="https://agnxiv.example",
        github_token="token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=None,
    )


def test_operational_slo_passes_healthy_snapshot() -> None:
    report = evaluate_operational_status(
        {
            "jobs_terminal_last_hour": 100,
            "stale_failures_last_hour": 1,
            "jobs_active": 4,
            "oldest_active_seconds": 120.0,
        },
        database_connected=True,
        transparency_valid=True,
    )
    assert report["passed"] is True
    assert report["status"] == "ok"


def test_operational_slo_detects_error_budget_and_integrity_breaches() -> None:
    report = evaluate_operational_status(
        {
            "jobs_terminal_last_hour": 100,
            "stale_failures_last_hour": 3,
            "jobs_active": 2,
            "oldest_active_seconds": 10.0,
        },
        database_connected=True,
        transparency_valid=False,
        policy=OperationalSLOPolicy(max_stale_failure_ratio=0.02),
    )
    assert report["passed"] is False
    assert "stale_callback_error_budget_exhausted" in report["breaches"]
    assert "transparency_chain_invalid" in report["breaches"]


def test_ops_status_requires_auth_and_is_healthy_for_empty_store(tmp_path: Path) -> None:
    app = create_app(_config(f"sqlite:///{tmp_path / 'ops.db'}"))
    with TestClient(app) as client:
        denied = client.get("/v1/ops/status")
        allowed = client.get(
            "/v1/ops/status",
            headers={"X-API-Key": "k" * 48},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["schema_version"] == "agnxiv.ops-status/1"
    assert body["passed"] is True
    assert body["transparency_valid"] is True
