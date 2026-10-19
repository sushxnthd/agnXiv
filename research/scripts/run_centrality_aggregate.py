from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--minimum-cases", type=int, default=75)
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--minimum-sources", type=int, default=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    reports = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in args.report
    ]
    cases: list[dict] = []
    sources: list[dict] = []

    for report in reports:
        details = report.get("cases_detail")
        if not isinstance(details, list):
            raise ValueError("centrality report is missing cases_detail")
        cases.extend(details)
        sources.append(
            {
                "schema_version": report.get("schema_version"),
                "evaluation_role": report.get("evaluation_role"),
                "source": report.get("source"),
                "cases": len(details),
                "recall_at_3": report.get("recall_at_3"),
                "recall_at_5": report.get("recall_at_5"),
            }
        )

    ids = [
        str(case.get("paper_id") or case.get("paper_key") or case.get("case_id") or "")
        for case in cases
    ]
    if any(not value for value in ids):
        raise ValueError("every aggregate case must expose a stable paper identifier")
    if len(set(ids)) != len(ids):
        raise ValueError("aggregate centrality sources contain duplicate paper identifiers")

    total = len(cases)
    r1 = sum(bool(case.get("recall_at_1")) for case in cases) / total if total else 0.0
    r3 = sum(bool(case.get("recall_at_3")) for case in cases) / total if total else 0.0
    r5 = sum(bool(case.get("recall_at_5")) for case in cases) / total if total else 0.0

    passed = (
        len(reports) >= args.minimum_sources
        and total >= args.minimum_cases
        and r3 >= args.min_recall_at_3
        and r5 >= args.min_recall_at_5
    )

    payload = {
        "schema_version": "agnxiv.centrality-production-aggregate/1",
        "evaluation_role": "heldout_external_multi_source",
        "sources": sources,
        "source_count": len(reports),
        "cases": total,
        "recall_at_1": r1,
        "recall_at_3": r3,
        "recall_at_5": r5,
        "thresholds": {
            "minimum_sources": args.minimum_sources,
            "minimum_cases": args.minimum_cases,
            "min_recall_at_3": args.min_recall_at_3,
            "min_recall_at_5": args.min_recall_at_5,
        },
        "passed": passed,
        "interpretation": (
            "Production centrality is evaluated over disjoint external paper sets "
            "from at least two independently curated metadata sources. The final "
            "sample-size threshold is applied to the aggregate, while each source "
            "retains its own case-level report."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))

    if not passed:
        raise SystemExit(
            "aggregate centrality gate failed: "
            f"sources={len(reports)}, n={total}, R@3={r3:.4f}, R@5={r5:.4f}"
        )


if __name__ == "__main__":
    main()
