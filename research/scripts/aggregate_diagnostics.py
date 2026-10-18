from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def aggregate(root: Path) -> dict:
    summaries = []
    for path in sorted(root.rglob("summary.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") == "agnxiv.research-diagnostic/1":
            summaries.append(payload)

    if not summaries:
        raise ValueError("no diagnostic summary.json files found")

    automation = [float(item["automation_score"]) for item in summaries]
    stages = sorted(
        {
            stage
            for item in summaries
            for stage in (item.get("stages") or {})
        }
    )
    stage_success = {
        stage: sum(bool(item.get("stages", {}).get(stage)) for item in summaries)
        / len(summaries)
        for stage in stages
    }

    centrality_rows = [
        item["centrality"] for item in summaries if item.get("centrality") is not None
    ]
    localization_rows = [
        item["localization"] for item in summaries if item.get("localization") is not None
    ]

    blockers = Counter(
        blocker
        for item in summaries
        for blocker in item.get("blockers", [])
    )

    environments = [item.get("environment") or {} for item in summaries]
    reproduction_ready = sum(
        bool(environment.get("reproduction_ready"))
        for environment in environments
    )
    dependency_sources = Counter(
        str(environment.get("dependency_source") or "unknown")
        for environment in environments
    )
    dependency_precision = Counter(
        str(environment.get("dependency_precision") or "unknown")
        for environment in environments
    )
    historical_fidelity = Counter(
        str(environment.get("historical_fidelity") or "unknown")
        for environment in environments
    )

    return {
        "schema_version": "agnxiv.research-diagnostic-summary/1",
        "evaluation_role": "diagnostic_nonblind",
        "cases": len(summaries),
        "case_ids": [item["case_id"] for item in summaries],
        "automation": {
            "mean": statistics.fmean(automation),
            "median": statistics.median(automation),
            "min": min(automation),
            "max": max(automation),
        },
        "stage_success_rate": stage_success,
        "environment": {
            "inference_rate": stage_success.get("environment_inference", 0.0),
            "reproduction_ready_rate": reproduction_ready / len(summaries),
            "dependency_source_counts": dict(dependency_sources),
            "dependency_precision_counts": dict(dependency_precision),
            "historical_fidelity_counts": dict(historical_fidelity),
        },
        "centrality": {
            "annotated_cases": len(centrality_rows),
            "recall_at_1": (
                sum(row["recall_at_1"] for row in centrality_rows)
                / len(centrality_rows)
                if centrality_rows else None
            ),
            "recall_at_3": (
                sum(row["recall_at_3"] for row in centrality_rows)
                / len(centrality_rows)
                if centrality_rows else None
            ),
            "recall_at_5": (
                sum(row["recall_at_5"] for row in centrality_rows)
                / len(centrality_rows)
                if centrality_rows else None
            ),
        },
        "localization": {
            "annotated_cases": len(localization_rows),
            "recall_at_5": (
                sum(row["recall_at_5"] for row in localization_rows)
                / len(localization_rows)
                if localization_rows else None
            ),
            "recall_at_10": (
                sum(row["recall_at_10"] for row in localization_rows)
                / len(localization_rows)
                if localization_rows else None
            ),
            "recall_at_25": (
                sum(row["recall_at_25"] for row in localization_rows)
                / len(localization_rows)
                if localization_rows else None
            ),
        },
        "blocker_counts": dict(blockers.most_common()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = aggregate(Path(args.input_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
