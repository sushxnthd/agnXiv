from agnxiv.build import BuildPlan, BuildResult
from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.pipeline import VerificationBundle
from agnxiv.provenance import ProvenanceManifest
from agnxiv.verdict_gate import gate_hosted_verdict
from agnxiv.verify import verify_numeric_claim


def _bundle(
    *,
    historical_fidelity: str,
    scope_resolution: str = "resolved",
    observed: float = 0.8,
) -> VerificationBundle:
    claim = Claim(id="C1", text="Accuracy is 0.9", metric="accuracy", reported_value=0.9)
    policy = VerificationPolicy(kind="absolute", tolerance=0.01)
    return VerificationBundle(
        claim=claim,
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0, tree_digest="a" * 64
        ),
        environment=EnvironmentSpec(
            historical_fidelity=historical_fidelity,
            scope_resolution=scope_resolution,
        ),
        record=verify_numeric_claim(claim, [Observation(value=observed)], policy),
    )


def _build(
    precision: str,
    *,
    image_id: str | None = None,
    base_image_id: str | None = None,
) -> BuildResult:
    return BuildResult(
        plan=BuildPlan(
            base_image="python:3.11-slim",
            dependency_file="requirements.txt",
            dependency_sha256="b" * 64,
            dependency_precision=precision,
            dockerfile="FROM python:3.11-slim\n",
            network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="agnxiv-env:test",
        image_id=image_id or "sha256:" + "c" * 64,
        base_image_id=base_image_id or "sha256:" + "d" * 64,
        stdout_sha256="e" * 64,
        stderr_sha256="f" * 64,
    )


def test_floating_approximate_contradiction_is_suppressed_but_measurements_survive() -> None:
    gated = gate_hosted_verdict(_bundle(historical_fidelity="approximate"), _build("floating"))

    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert gated.provisional_verdict == Verdict.CONTRADICTED
    assert gated.record.expected == 0.9
    assert gated.record.observed_mean == 0.8
    assert len(gated.verdict_gate_reasons) == 2


def test_direct_version_pins_do_not_certify_transitive_artifacts() -> None:
    gated = gate_hosted_verdict(_bundle(historical_fidelity="constrained"), _build("version-pinned"))

    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert gated.provisional_verdict == Verdict.CONTRADICTED
    assert "not hash-pinned" in gated.verdict_gate_reasons[0]


def test_hash_pinned_constrained_control_remains_decisive() -> None:
    original = _bundle(historical_fidelity="constrained")
    gated = gate_hosted_verdict(original, _build("hash-pinned"))

    assert gated.record.verdict == Verdict.CONTRADICTED
    assert gated.provisional_verdict is None
    assert gated.verdict_gate_reasons == []


def test_ambiguous_scope_is_suppressed_even_with_hashes() -> None:
    gated = gate_hosted_verdict(
        _bundle(historical_fidelity="constrained", scope_resolution="ambiguous"),
        _build("hash-pinned"),
    )

    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("ambiguous" in reason for reason in gated.verdict_gate_reasons)


def test_malformed_built_image_identity_is_suppressed() -> None:
    gated = gate_hosted_verdict(
        _bundle(historical_fidelity="constrained"),
        _build("hash-pinned", image_id="sha256:built"),
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert gated.provisional_verdict == Verdict.CONTRADICTED
    assert any("built environment" in reason for reason in gated.verdict_gate_reasons)


def test_malformed_base_image_identity_is_suppressed() -> None:
    gated = gate_hosted_verdict(
        _bundle(historical_fidelity="constrained"),
        _build("hash-pinned", base_image_id="sha256:" + "D" * 64),
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert gated.provisional_verdict == Verdict.CONTRADICTED
    assert any("base image" in reason for reason in gated.verdict_gate_reasons)


def test_existing_abstention_is_not_rewritten() -> None:
    bundle = _bundle(historical_fidelity="approximate")
    bundle.record.verdict = Verdict.UNABLE_TO_VERIFY
    gated = gate_hosted_verdict(bundle, _build("floating"))

    assert gated is bundle
    assert gated.provisional_verdict is None
