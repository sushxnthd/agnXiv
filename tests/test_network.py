from agnxiv.network import (
    AttemptStatus,
    EvidenceAttempt,
    ScientificRecord,
    attempt_from_github_payload,
)


def test_record_preserves_mixed_evidence() -> None:
    record = ScientificRecord(
        paper_id="1403.6652",
        attempts=[
            EvidenceAttempt(
                attempt_id="AX-1",
                paper_id="1403.6652",
                repository="owner/repo",
                repository_ref="main",
                status=AttemptStatus.REPRODUCED,
            ),
            EvidenceAttempt(
                attempt_id="AX-2",
                paper_id="1403.6652",
                repository="owner/repo",
                repository_ref="main",
                status=AttemptStatus.RESULT_DIVERGENCE,
            ),
        ],
    )

    summary = record.summary()
    assert summary.current_state == "MIXED_EVIDENCE"
    assert summary.reproduced == 1
    assert summary.divergences == 1


def test_auto_plan_becomes_evidence_incomplete_attempt() -> None:
    attempt = attempt_from_github_payload(
        {
            "request": {
                "repository": "phanein/deepwalk",
                "repository_ref": "main",
                "arxiv_id": "1403.6652",
            },
            "status": "needs_review",
            "result": {
                "kind": "auto_plan",
                "repository_commit": "abc123",
                "plan": {
                    "automation_score": 8 / 9,
                    "safe_to_execute": False,
                    "blockers": ["historical dependency sensitivity"],
                },
            },
            "error": None,
        },
        attempt_id="AX-GH-26",
    )

    assert attempt.status == AttemptStatus.EVIDENCE_INCOMPLETE
    assert attempt.automation_score == 8 / 9
    assert attempt.pinned_commit == "abc123"


def test_contradicted_verdict_is_neutral_result_divergence() -> None:
    attempt = attempt_from_github_payload(
        {
            "request": {
                "repository": "owner/repo",
                "repository_ref": "v1",
                "arxiv_id": "2601.00001",
            },
            "status": "completed",
            "result": {
                "kind": "verification",
                "bundle": {
                    "claim": {"id": "C1", "text": "Accuracy is 0.9"},
                    "record": {
                        "verdict": "CONTRADICTED",
                        "expected": 0.9,
                        "observed_mean": 0.7,
                    },
                    "provenance": {"git": {"commit": "deadbeef"}},
                },
            },
            "error": None,
        },
        attempt_id="AX-GH-99",
    )

    assert attempt.status == AttemptStatus.RESULT_DIVERGENCE
    assert attempt.verdict.value == "CONTRADICTED"
    assert attempt.observed == 0.7
