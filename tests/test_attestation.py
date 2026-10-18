from pathlib import Path

from agnxiv.attestation import attest_bundle
from agnxiv.models import Claim, VerificationPolicy
from agnxiv.pipeline import VerificationBundle
from agnxiv.environment import EnvironmentSpec
from agnxiv.provenance import fingerprint_tree
from agnxiv.verify import verify_numeric_claim
from agnxiv.models import Observation


def test_attestation_is_bound_to_bundle_contents(tmp_path: Path) -> None:
    (tmp_path / "analysis.py").write_text("print('accuracy: 90%')\n", encoding="utf-8")
    provenance = fingerprint_tree(tmp_path)
    claim = Claim(id="C1", text="Accuracy is 90%.", reported_value=0.9)
    policy = VerificationPolicy(kind="relative", tolerance=0.01)
    record = verify_numeric_claim(claim, [Observation(value=0.9)], policy)

    bundle = VerificationBundle(
        claim=claim,
        provenance=provenance,
        environment=EnvironmentSpec(),
        record=record,
    )
    first = attest_bundle(bundle)
    bundle.record.rationale = "changed"
    second = attest_bundle(bundle)

    assert first.bundle_sha256 != second.bundle_sha256
    assert first.repository_tree_sha256 == provenance.tree_digest
