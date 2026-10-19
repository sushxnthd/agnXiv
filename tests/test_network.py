from agnxiv.network import (
    AttemptStatus,
    EvidenceAttempt,
    EvidenceGrade,
    ScientificRecord,
    aggregate_claim_evidence,
    attempt_from_github_payload,
    attempts_from_github_payload,
)


def test_record_preserves_mixed_independent_evidence() -> None:
    record = ScientificRecord(
        paper_id="1403.6652",
        attempts=[
            EvidenceAttempt(
                attempt_id="AX-1",
                paper_id="1403.6652",
                claim_id="C1",
                repository="owner/repo-a",
                repository_ref="main",
                status=AttemptStatus.REPRODUCED,
                evidence_grade=EvidenceGrade.STRONG,
                independence_key="implementation-a",
            ),
            EvidenceAttempt(
                attempt_id="AX-2",
                paper_id="1403.6652",
                claim_id="C1",
                repository="owner/repo-b",
                repository_ref="main",
                status=AttemptStatus.RESULT_DIVERGENCE,
                evidence_grade=EvidenceGrade.STRONG,
                independence_key="implementation-b",
            ),
        ],
    )

    summary = record.summary()
    assert summary.current_state == "MIXED_EVIDENCE"
    assert summary.reproduced == 1
    assert summary.divergences == 1
    assert summary.claim_states[0].independent_clusters == 2


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



def _verification_bundle(
    *,
    claim_id: str,
    verdict: str,
    expected: float,
    observed: float,
    commit: str = "deadbeef",
) -> dict:
    return {
        "claim": {
            "id": claim_id,
            "text": f"Claim {claim_id}",
            "metric": "accuracy",
        },
        "record": {
            "verdict": verdict,
            "expected": expected,
            "observed_mean": observed,
        },
        "provenance": {"git": {"commit": commit}},
        "observation_method": "explicit_regex",
        "execution": {
            "returncode": 0,
            "source_unchanged": True,
            "artifacts_unchanged": True,
        },
        "artifacts": [],
    }


def test_multi_claim_payload_preserves_all_verification_attempts() -> None:
    payload = {
        "request": {
            "repository": "owner/repo",
            "repository_ref": "deadbeef",
            "arxiv_id": "2601.00001",
        },
        "status": "succeeded",
        "result": {
            "kind": "verification",
            "zero_manifest": True,
            "build": {"plan": {"dependency_precision": "floating"}},
            "bundle": _verification_bundle(
                claim_id="C1",
                verdict="VERIFIED",
                expected=0.9,
                observed=0.9,
            ),
            "additional_verifications": [
                {
                    "bundle": _verification_bundle(
                        claim_id="C2",
                        verdict="CONTRADICTED",
                        expected=0.8,
                        observed=0.7,
                    )
                }
            ],
        },
        "error": None,
    }

    attempts = attempts_from_github_payload(payload, attempt_id="AX-GH-7")

    assert [item.attempt_id for item in attempts] == ["AX-GH-7", "AX-GH-7-C2"]
    assert [item.claim_id for item in attempts] == ["C1", "C2"]
    assert all(item.evidence_grade == EvidenceGrade.CONDITIONAL for item in attempts)
    assert attempts[0].independence_key == attempts[1].independence_key


def test_version_pinned_explicit_execution_remains_conditional() -> None:
    payload = {
        "request": {
            "repository": "owner/repo",
            "repository_ref": "deadbeef",
            "arxiv_id": "2601.00001",
        },
        "status": "succeeded",
        "result": {
            "kind": "verification",
            "build": {"plan": {"dependency_precision": "version-pinned"}},
            "environment": {"historical_fidelity": "constrained"},
            "bundle": _verification_bundle(
                claim_id="C1",
                verdict="VERIFIED",
                expected=0.9,
                observed=0.9,
            ),
        },
        "error": None,
    }

    attempt = attempt_from_github_payload(payload, attempt_id="AX-1")

    assert attempt.evidence_grade == EvidenceGrade.CONDITIONAL
    assert attempt.observation_method == "explicit_regex"
    assert attempt.dependency_precision == "version-pinned"


def test_hash_pinned_historically_constrained_execution_is_strong() -> None:
    payload = {
        "request": {
            "repository": "owner/repo",
            "repository_ref": "deadbeef",
            "arxiv_id": "2601.00001",
        },
        "status": "succeeded",
        "result": {
            "kind": "verification",
            "build": {"plan": {"dependency_precision": "hash-pinned"}},
            "environment": {"historical_fidelity": "constrained"},
            "bundle": _verification_bundle(
                claim_id="C1",
                verdict="VERIFIED",
                expected=0.9,
                observed=0.9,
            ),
        },
        "error": None,
    }

    attempt = attempt_from_github_payload(payload, attempt_id="AX-2")

    assert attempt.evidence_grade == EvidenceGrade.STRONG
    assert attempt.dependency_precision == "hash-pinned"


def test_hash_pinned_without_historical_fidelity_is_conditional() -> None:
    payload = {
        "request": {
            "repository": "owner/repo",
            "repository_ref": "deadbeef",
            "arxiv_id": "2601.00001",
        },
        "status": "succeeded",
        "result": {
            "kind": "verification",
            "build": {"plan": {"dependency_precision": "hash-pinned"}},
            "bundle": _verification_bundle(
                claim_id="C1",
                verdict="VERIFIED",
                expected=0.9,
                observed=0.9,
            ),
        },
        "error": None,
    }

    attempt = attempt_from_github_payload(payload, attempt_id="AX-3")

    assert attempt.evidence_grade == EvidenceGrade.CONDITIONAL


def test_floating_dependency_divergence_remains_conditional_at_record_level() -> None:
    attempt = EvidenceAttempt(
        attempt_id="AX-1",
        paper_id="p",
        claim_id="C1",
        repository="owner/repo",
        repository_ref="main",
        pinned_commit="abc",
        status=AttemptStatus.RESULT_DIVERGENCE,
        evidence_grade=EvidenceGrade.CONDITIONAL,
        independence_key="cluster-a",
    )
    summary = ScientificRecord(paper_id="p", attempts=[attempt]).summary()

    assert summary.current_state == "CONDITIONAL_EVIDENCE"
    assert summary.claim_states[0].conditional_divergent_clusters == 1
    assert summary.claim_states[0].strong_divergent_clusters == 0


def test_repeated_same_cluster_does_not_count_as_independent_votes() -> None:
    attempts = [
        EvidenceAttempt(
            attempt_id=f"AX-{index}",
            claim_id="C1",
            repository="owner/repo",
            repository_ref="main",
            status=AttemptStatus.REPRODUCED,
            evidence_grade=EvidenceGrade.STRONG,
            independence_key="same-code-and-data",
        )
        for index in range(3)
    ]
    summary = aggregate_claim_evidence(attempts)[0]

    assert summary.attempts == 3
    assert summary.independent_clusters == 1
    assert summary.strong_reproduced_clusters == 1


def test_conflict_inside_same_evidence_cluster_is_not_mixed_independent_evidence() -> None:
    attempts = [
        EvidenceAttempt(
            attempt_id="AX-1",
            claim_id="C1",
            repository="owner/repo",
            repository_ref="main",
            status=AttemptStatus.REPRODUCED,
            evidence_grade=EvidenceGrade.STRONG,
            independence_key="same-cluster",
        ),
        EvidenceAttempt(
            attempt_id="AX-2",
            claim_id="C1",
            repository="owner/repo",
            repository_ref="main",
            status=AttemptStatus.RESULT_DIVERGENCE,
            evidence_grade=EvidenceGrade.STRONG,
            independence_key="same-cluster",
        ),
    ]
    summary = aggregate_claim_evidence(attempts)[0]

    assert summary.current_state == "CLUSTER_CONFLICT"
    assert summary.conflicting_clusters == 1
    assert summary.independent_clusters == 1


def test_independent_strong_clusters_can_produce_mixed_evidence() -> None:
    attempts = [
        EvidenceAttempt(
            attempt_id="AX-A",
            claim_id="C1",
            repository="owner/a",
            repository_ref="main",
            status=AttemptStatus.REPRODUCED,
            evidence_grade=EvidenceGrade.STRONG,
            independence_key="independent-a",
        ),
        EvidenceAttempt(
            attempt_id="AX-B",
            claim_id="C1",
            repository="owner/b",
            repository_ref="main",
            status=AttemptStatus.RESULT_DIVERGENCE,
            evidence_grade=EvidenceGrade.STRONG,
            independence_key="independent-b",
        ),
    ]
    summary = aggregate_claim_evidence(attempts)[0]

    assert summary.current_state == "MIXED_EVIDENCE"
    assert summary.independent_clusters == 2
