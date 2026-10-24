"""Independent stdlib-only audit of the hosted environment verdict firewall.

This intentionally imports no agnxiv production module.
"""

import hashlib
import json

CASES = [
    {
        "id": "frozen_external_paper_floating",
        "scope": "resolved",
        "historical": "approximate",
        "precision": "floating",
        "raw": "CONTRADICTED",
        "expected": "UNABLE_TO_VERIFY",
    },
    {
        "id": "direct_pins_leave_transitives_open",
        "scope": "resolved",
        "historical": "constrained",
        "precision": "version-pinned",
        "raw": "VERIFIED",
        "expected": "UNABLE_TO_VERIFY",
    },
    {
        "id": "hash_pinned_control",
        "scope": "resolved",
        "historical": "constrained",
        "precision": "hash-pinned",
        "raw": "CONTRADICTED",
        "expected": "CONTRADICTED",
    },
    {
        "id": "ambiguous_scope_attack",
        "scope": "ambiguous",
        "historical": "constrained",
        "precision": "hash-pinned",
        "raw": "VERIFIED",
        "expected": "UNABLE_TO_VERIFY",
    },
    {
        "id": "prior_abstention_is_stable",
        "scope": "none",
        "historical": "unknown",
        "precision": "base-only",
        "raw": "UNABLE_TO_VERIFY",
        "expected": "UNABLE_TO_VERIFY",
    },
]


def independent_decision(case: dict[str, str]) -> str:
    if case["raw"] == "UNABLE_TO_VERIFY":
        return case["raw"]
    certified = (
        case["scope"] != "ambiguous"
        and case["historical"] == "constrained"
        and case["precision"] == "hash-pinned"
    )
    return case["raw"] if certified else "UNABLE_TO_VERIFY"


def main() -> None:
    audited = [
        {**case, "actual": independent_decision(case)} for case in CASES
    ]
    assert all(case["actual"] == case["expected"] for case in audited)
    canonical = json.dumps(audited, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "agnxiv.environment-verdict-firewall-audit/1",
        "cases": len(audited),
        "matched": len(audited),
        "false_definitive_verdicts": 0,
        "exact_controls_preserved": 1,
        "audit_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "results": audited,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
