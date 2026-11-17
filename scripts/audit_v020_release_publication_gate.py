#!/usr/bin/env python3
"""Independent, zero-production-import audit of the v0.2.0 release gate."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

RESULT = Path("results/v020_release_publication_gate/results.json")
WORKFLOW = Path(".github/workflows/publish-v0.2.0.yml")
OUT = Path("results/v020_release_publication_gate/audit.json")


def independent_preflight_counts() -> dict:
    accepted = 0
    total = 0
    for confirmation, commit_format, head_match, state, target_match in itertools.product(
        (False, True),
        (False, True),
        (False, True),
        ("absent", "draft", "tag_only", "published"),
        (False, True),
    ):
        total += 1
        target_safe = (state == "absent" and target_match) or (
            state in {"draft", "tag_only"} and target_match
        )
        accepted += (
            confirmation
            and commit_format
            and head_match
            and state in {"absent", "draft", "tag_only"}
            and target_safe
        )
    return {"total": total, "accepted": accepted, "rejected": total - accepted}


def independent_asset_counts() -> dict:
    decisions = tuple(all(bits) for bits in itertools.product((False, True), repeat=10))
    return {
        "total": len(decisions),
        "accepted": sum(decisions),
        "rejected": len(decisions) - sum(decisions),
    }


def main() -> None:
    result_bytes = RESULT.read_bytes()
    result = json.loads(result_bytes)
    workflow = WORKFLOW.read_text(encoding="utf-8")
    preflight = independent_preflight_counts()
    assets = independent_asset_counts()
    call_preflight = workflow.index("verify_v020_release_publication_gate.py preflight")
    create_draft = workflow.index('gh release create "$RELEASE_TAG"')
    call_assets = workflow.index("verify_v020_release_publication_gate.py assets")
    publish = workflow.index('gh release edit "$RELEASE_TAG" --draft=false')
    ordering = call_preflight < create_draft < call_assets < publish
    passed = (
        result["schema"] == "agnxiv.release-publication-gate/1"
        and result["overall_passed"] is True
        and result["preflight"]
        == {
            "accepted_controls": preflight["accepted"],
            "false_passes": 0,
            "false_rejects": 0,
            "rejected_cases": preflight["rejected"],
            "total_cases": preflight["total"],
        }
        and result["postdraft_assets"]
        == {
            "accepted_controls": assets["accepted"],
            "false_passes": 0,
            "false_rejects": 0,
            "rejected_cases": assets["rejected"],
            "total_cases": assets["total"],
        }
        and ordering
        and "environment: agnxiv-release" in workflow
        and "contents: write" in workflow
        and "workflow_dispatch:" in workflow
    )
    report = {
        "schema": "agnxiv.release-publication-gate-audit/1",
        "production_imports": 0,
        "independent_method": "Boolean state enumeration plus workflow ordering audit",
        "results_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "preflight_cases_recomputed": preflight,
        "postdraft_cases_recomputed": assets,
        "workflow_ordering": {
            "preflight_before_draft": call_preflight < create_draft,
            "draft_before_asset_gate": create_draft < call_assets,
            "asset_gate_before_publication": call_assets < publish,
        },
        "passed": passed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
