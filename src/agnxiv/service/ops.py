from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OperationalSLOPolicy:
    max_stale_failure_ratio: float = 0.02
    min_terminal_samples: int = 20
    max_active_jobs: int = 100
    max_oldest_active_seconds: float = 45 * 60


def evaluate_operational_status(
    metrics: dict[str, Any],
    *,
    database_connected: bool,
    transparency_valid: bool,
    policy: OperationalSLOPolicy | None = None,
) -> dict[str, Any]:
    active = policy or OperationalSLOPolicy()
    breaches: list[str] = []

    terminal = int(metrics.get("jobs_terminal_last_hour", 0) or 0)
    stale = int(metrics.get("stale_failures_last_hour", 0) or 0)
    stale_ratio = stale / terminal if terminal else 0.0
    active_jobs = int(metrics.get("jobs_active", 0) or 0)
    oldest = float(metrics.get("oldest_active_seconds", 0.0) or 0.0)

    if not database_connected:
        breaches.append("database_unreachable")
    if not transparency_valid:
        breaches.append("transparency_chain_invalid")
    if active_jobs > active.max_active_jobs:
        breaches.append("active_job_capacity_exceeded")
    if oldest > active.max_oldest_active_seconds:
        breaches.append("active_job_age_slo_breached")
    if terminal >= active.min_terminal_samples and stale_ratio > active.max_stale_failure_ratio:
        breaches.append("stale_callback_error_budget_exhausted")

    return {
        "schema_version": "agnxiv.ops-status/1",
        "status": "ok" if not breaches else "degraded",
        "passed": not breaches,
        "breaches": breaches,
        "database_connected": database_connected,
        "transparency_valid": transparency_valid,
        "metrics": metrics,
        "slo": {
            **asdict(active),
            "stale_failure_ratio_last_hour": stale_ratio,
            "stale_failure_budget_remaining": max(
                0.0,
                active.max_stale_failure_ratio - stale_ratio,
            ),
        },
    }
