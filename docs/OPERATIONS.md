# Operations and SLOs

## Operational status

The authenticated `GET /v1/ops/status` endpoint evaluates the hosted control
plane against a fail-closed SLO contract:

- PostgreSQL must be reachable;
- the transparency hash chain must verify;
- active jobs must remain within the configured capacity;
- the oldest active job must remain inside the stale-job deadline;
- once there are at least 20 terminal jobs in the last hour, stale callback
  failures may consume at most 2% of that hourly terminal-job budget.

A breach returns HTTP 503 with a secret-free list of breach codes.

## Alerting

`.github/workflows/ops-slo-monitor.yml` runs the SLO contract in CI and has a
scheduled production watcher every 15 minutes. A deployment enables the live
watcher by configuring:

- repository variable `AGNXIV_PRODUCTION_URL`;
- repository secret `AGNXIV_MONITOR_API_KEY`.

The watcher fails if `/readyz` or `/v1/ops/status` fails, so the configured
GitHub Actions notification/escalation path becomes the alert transport.

## Recovery

PostgreSQL backup/restore is tested separately from the cross-region drill.
The cross-region drill restores a primary recovery point into an independent
secondary PostgreSQL server, stops the primary, and verifies jobs plus the
append-only transparency chain from the secondary.

See `docs/DISASTER_RECOVERY.md` for topology, RPO/RTO semantics, and deployment
responsibilities.
