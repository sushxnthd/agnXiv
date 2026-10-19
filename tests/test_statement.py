import base64
import json
from pathlib import Path

import pytest

from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, VerificationPolicy
from agnxiv.pipeline import VerificationBundle
from agnxiv.provenance import (
    fingerprint_artifact,
    fingerprint_document,
    fingerprint_tree,
)
from agnxiv.service.app import _enrich_signed_result
from agnxiv.service.config import ServiceConfig
from agnxiv.statement import (
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    AttestationSignatureError,
    DSSEEnvelope,
    build_verification_statement,
    generate_ed25519_keypair,
    sign_statement_ed25519,
    verify_statement_ed25519,
)
from agnxiv.verify import verify_numeric_claim


def _bundle(tmp_path: Path) -> VerificationBundle:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "analysis.py").write_text("print('accuracy: 90%')\n", encoding="utf-8")

    manuscript = tmp_path / "paper.txt"
    manuscript.write_text("Accuracy is 90%.\n", encoding="utf-8")

    artifact = tmp_path / "data.csv"
    artifact.write_text("x,y\n1,2\n", encoding="utf-8")

    claim = Claim(id="C1", text="Accuracy is 90%.", reported_value=0.9)
    policy = VerificationPolicy(kind="relative", tolerance=0.01)
    record = verify_numeric_claim(claim, [Observation(value=0.9)], policy)

    return VerificationBundle(
        claim=claim,
        manuscript=fingerprint_document(manuscript),
        provenance=fingerprint_tree(repository),
        artifacts=[fingerprint_artifact(artifact)],
        environment=EnvironmentSpec(),
        observation_method="explicit_json_path",
        observation_locator="metrics.accuracy",
        record=record,
    )


def test_statement_binds_manuscript_repository_and_artifact(tmp_path: Path) -> None:
    statement = build_verification_statement(_bundle(tmp_path))

    assert statement["_type"] == STATEMENT_TYPE
    assert statement["predicateType"] == PREDICATE_TYPE
    assert len(statement["subject"]) == 3
    assert statement["predicate"]["result"]["verdict"] == "VERIFIED"


def test_ed25519_dsse_round_trip(tmp_path: Path) -> None:
    statement = build_verification_statement(_bundle(tmp_path))
    private_key, public_key, key_id = generate_ed25519_keypair()

    envelope = sign_statement_ed25519(statement, private_key)
    verified = verify_statement_ed25519(envelope, public_key)

    assert verified == statement
    assert envelope.signatures[0].keyid == key_id


def test_tampered_dsse_payload_is_rejected(tmp_path: Path) -> None:
    statement = build_verification_statement(_bundle(tmp_path))
    private_key, public_key, _ = generate_ed25519_keypair()
    envelope = sign_statement_ed25519(statement, private_key)

    payload = json.loads(base64.b64decode(envelope.payload))
    payload["predicate"]["result"]["verdict"] = "CONTRADICTED"
    envelope.payload = base64.b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    with pytest.raises(AttestationSignatureError):
        verify_statement_ed25519(envelope, public_key)


def test_tampered_payload_type_is_rejected(tmp_path: Path) -> None:
    statement = build_verification_statement(_bundle(tmp_path))
    private_key, public_key, _ = generate_ed25519_keypair()
    envelope = sign_statement_ed25519(statement, private_key)
    envelope.payloadType = "application/json"

    with pytest.raises(AttestationSignatureError):
        verify_statement_ed25519(envelope, public_key)


def test_hosted_signature_binds_exact_actions_run_identity(tmp_path: Path) -> None:
    private_key, public_key, _ = generate_ed25519_keypair()
    config = ServiceConfig(
        database_url="postgresql://user:pass@example/db",
        api_keys=("k" * 48,),
        public_base_url="https://agnxiv.example",
        github_token="token",
        github_repository="sushxnthd/agnXiv",
        github_ref="refs/tags/agnxiv-test-release",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=base64.b64encode(private_key).decode("ascii"),
        github_workflow_sha="a" * 40,
    )
    result = {
        "kind": "verification",
        "bundle": _bundle(tmp_path).model_dump(mode="json"),
    }

    enriched = _enrich_signed_result(
        config,
        result,
        workflow_run_id=12345,
    )

    assert enriched is not None
    assert enriched["orchestration"] == {
        "provider": "github-actions",
        "workflow_run_id": 12345,
    }
    assert enriched["statement"]["predicate"]["orchestration"] == {
        "provider": "github-actions",
        "workflowRunId": 12345,
    }

    envelope = DSSEEnvelope.model_validate(enriched["dsseEnvelope"])
    verified = verify_statement_ed25519(envelope, public_key)
    assert verified["predicate"]["orchestration"]["workflowRunId"] == 12345
