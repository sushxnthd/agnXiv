from agnxiv.safety_confidence import (
    SafetyDecision,
    false_pass_confidence,
    minimum_zero_error_sample,
)


def _row(case_id: str, truth: str, decision: str) -> SafetyDecision:
    return SafetyDecision(
        case_id=case_id,
        independence_key="cluster-" + case_id,
        ground_truth=truth,
        decision=decision,
        source="held-out-test",
    )


def test_zero_error_release_sample_is_299_at_one_percent_target() -> None:
    assert minimum_zero_error_sample(target_upper_bound=0.01, alpha=0.05) == 299


def test_zero_false_passes_use_exact_one_sided_bound() -> None:
    rows = [_row(str(i), "supports", "supports") for i in range(299)]
    report = false_pass_confidence(rows)

    assert report.false_passes == 0
    assert report.zero_false_pass_upper_bound is not None
    assert report.one_sided_upper_bound == report.zero_false_pass_upper_bound
    assert report.one_sided_upper_bound <= 0.01
    assert report.production_pass is True


def test_observed_false_pass_still_reports_uncertainty_bound() -> None:
    rows = [_row(str(i), "supports", "supports") for i in range(99)]
    rows.append(_row("bad", "not_supports", "supports"))

    report = false_pass_confidence(rows)

    assert report.false_passes == 1
    assert report.zero_false_pass_upper_bound is None
    assert report.one_sided_upper_bound is not None
    assert report.one_sided_upper_bound > 0.01
    assert report.production_pass is False


def test_duplicate_evidence_clusters_never_satisfy_release_gate() -> None:
    rows = [
        SafetyDecision(
            case_id=str(i),
            independence_key="same-cluster",
            ground_truth="supports",
            decision="supports",
            source="held-out-test",
        )
        for i in range(299)
    ]
    report = false_pass_confidence(rows)

    assert report.independent_supports is False
    assert report.production_pass is False
