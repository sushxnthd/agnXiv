#!/usr/bin/env python3
"""Execute the frozen digest-attestation transparency-inclusion matrix."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from verify_authority_registry_checkpoint_artifact_scope import (
    CONSUMER,
    EXECUTION,
    artifact_scope,
    envelopes,
)
from verify_authority_registry_checkpoint_digest_attestation_auth import (
    TRUSTED_PRIVATE,
    TRUSTED_PUBLIC,
)
from verify_authority_registry_checkpoint_digest_producer import TRUSTED as PRODUCER
from verify_authority_registry_checkpoint_digest_profile import TRUSTED as PROFILE
from verify_authority_registry_checkpoint_history_commitment import (
    FAMILIES,
    attest,
    bundle,
    chain,
    gate,
)

from agnxiv.authority import (
    RegistryCheckpointDigestAttestationScope,
    RegistryCheckpointTransparencyInclusionWitness,
    registry_checkpoint_digest_attestation_key_sha256,
    registry_checkpoint_digest_attestation_scoped_history_commitment_sha256,
    registry_checkpoint_digest_producer_scoped_history_commitment_sha256,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
    registry_checkpoint_transparency_inclusion_witness_sha256,
    sign_registry_checkpoint_digest_attestation,
)
from agnxiv.models import Verdict

OUT = Path(
    "research/results/authority-registry-checkpoint-transparency-inclusion.json.gz"
)
SUMMARY = Path(
    "research/results/authority-registry-checkpoint-transparency-inclusion-summary.json"
)
PROVENANCE = "4" * 64
FAMILIES_INCLUSION = (
    "missing_witness",
    "tampered_audit_path",
    "wrong_leaf_index",
    "wrong_tree_root",
)


def leaf_hash(statement_sha256):
    return hashlib.sha256(b"\x00" + bytes.fromhex(statement_sha256)).digest()


def node_hash(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def valid_witness():
    statements = [f"{digit:x}" * 64 for digit in range(1, 9)]
    statements[3] = PROVENANCE
    level0 = [leaf_hash(statement) for statement in statements]
    level1 = [node_hash(level0[index], level0[index + 1]) for index in range(0, 8, 2)]
    level2 = [node_hash(level1[index], level1[index + 1]) for index in range(0, 4, 2)]
    root = node_hash(level2[0], level2[1])
    return RegistryCheckpointTransparencyInclusionWitness(
        log_id="agnxiv-research-log-v1",
        tree_size=8,
        leaf_index=3,
        root_sha256=root.hex(),
        audit_path_sha256=[level0[2].hex(), level1[0].hex(), level2[1].hex()],
    )


VALID_WITNESS = valid_witness()


def scope_for(witness):
    digest = (
        registry_checkpoint_transparency_inclusion_witness_sha256(witness)
        if witness is not None
        else "6" * 64
    )
    return RegistryCheckpointDigestAttestationScope(
        predicate_type="https://slsa.dev/provenance/v1",
        provenance_statement_sha256=PROVENANCE,
        attestation_signer_key_sha256=(
            registry_checkpoint_digest_attestation_key_sha256(TRUSTED_PUBLIC)
        ),
        transparency_inclusion_witness_sha256=digest,
    )


def witness_for(family, control):
    if control:
        return VALID_WITNESS
    if family == "missing_witness":
        return None
    if family == "tampered_audit_path":
        path = list(VALID_WITNESS.audit_path_sha256)
        path[0] = "0" * 64
        return VALID_WITNESS.model_copy(update={"audit_path_sha256": path})
    if family == "wrong_leaf_index":
        return VALID_WITNESS.model_copy(update={"leaf_index": 2})
    if family == "wrong_tree_root":
        return VALID_WITNESS.model_copy(update={"root_sha256": "f" * 64})
    raise AssertionError(family)


def run_case(case, family_index, *, control=False):
    family = FAMILIES_INCLUSION[family_index]
    rows = chain(FAMILIES[family_index], recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    artifact = artifact_scope(item)
    consumer, execution, artifact_commitment = envelopes(rows["commitment"], artifact)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact_commitment, PROFILE
    )
    producer = registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
        profile, PRODUCER
    )
    witness = witness_for(family, control)
    scope = scope_for(witness)
    attestation_commitment = (
        registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
            producer, scope
        )
    )
    signed = sign_registry_checkpoint_digest_attestation(scope, TRUSTED_PRIVATE)
    common = {
        "commitment": rows["commitment"],
        "require_commitment": True,
        "consumer_scope": CONSUMER,
        "scoped_commitment": consumer,
        "require_consumer_scope": True,
        "execution_scope": EXECUTION,
        "execution_scoped_commitment": execution,
        "require_execution_scope": True,
        "artifact_scope": artifact,
        "artifact_scoped_commitment": artifact_commitment,
        "require_artifact_scope": True,
        "digest_profile": PROFILE,
        "digest_profile_scoped_commitment": profile,
        "require_digest_profile": True,
        "producer_scope": PRODUCER,
        "producer_scoped_commitment": producer,
        "require_producer_scope": True,
        "attestation_scope": scope,
        "attestation_scoped_commitment": attestation_commitment,
        "require_attestation_scope": True,
        "signed_attestation": signed,
        "trusted_attestation_public_key_pem": TRUSTED_PUBLIC,
        "require_attestation_authentication": True,
    }
    parent = gate(item.model_copy(deep=True), rows, **common)
    corrected = gate(
        item.model_copy(deep=True),
        rows,
        **common,
        transparency_inclusion_witness=witness,
        require_transparency_inclusion=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "scope": scope.model_dump(mode="json"),
        "signed_attestation": signed.model_dump(mode="json"),
        "trusted_public_key_pem": TRUSTED_PUBLIC,
        "witness": None if witness is None else witness.model_dump(mode="json"),
        "signature_authenticated_definitive": (
            parent.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "inclusion_verified_definitive": (
            corrected.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "inclusion_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(276000)
    attest(item, rows["final"])
    artifact = artifact_scope(item)
    consumer, execution, artifact_commitment = envelopes(rows["commitment"], artifact)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact_commitment, PROFILE
    )
    producer = registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
        profile, PRODUCER
    )
    scope = scope_for(VALID_WITNESS)
    commitment = registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
        producer, scope
    )
    signed = sign_registry_checkpoint_digest_attestation(scope, TRUSTED_PRIVATE)

    def blocked(*, witness=VALID_WITNESS, require_auth=True):
        result = gate(
            item.model_copy(deep=True),
            rows,
            commitment=rows["commitment"],
            require_commitment=True,
            consumer_scope=CONSUMER,
            scoped_commitment=consumer,
            require_consumer_scope=True,
            execution_scope=EXECUTION,
            execution_scoped_commitment=execution,
            require_execution_scope=True,
            artifact_scope=artifact,
            artifact_scoped_commitment=artifact_commitment,
            require_artifact_scope=True,
            digest_profile=PROFILE,
            digest_profile_scoped_commitment=profile,
            require_digest_profile=True,
            producer_scope=PRODUCER,
            producer_scoped_commitment=producer,
            require_producer_scope=True,
            attestation_scope=scope,
            attestation_scoped_commitment=commitment,
            require_attestation_scope=True,
            signed_attestation=signed,
            trusted_attestation_public_key_pem=TRUSTED_PUBLIC,
            require_attestation_authentication=require_auth,
            transparency_inclusion_witness=witness,
            require_transparency_inclusion=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    mismatch = VALID_WITNESS.model_copy(update={"root_sha256": "e" * 64})
    invalid_index = VALID_WITNESS.model_copy(update={"leaf_index": 8})
    return {
        "missing_witness_blocked": blocked(witness=None),
        "without_authentication_mode_blocked": blocked(require_auth=False),
        "witness_commitment_mismatch_blocked": blocked(witness=mismatch),
        "invalid_leaf_index_blocked": blocked(witness=invalid_index),
    }


def main():
    attacks = [
        run_case(271000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [
        run_case(275000 + offset, offset % 4, control=True) for offset in range(32)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "signature_authenticated_false_passes": sum(
            row["signature_authenticated_definitive"] for row in attacks
        ),
        "inclusion_verified_false_passes": sum(
            row["inclusion_verified_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "inclusion_verified_controls_passed": sum(
            row["inclusion_verified_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["inclusion_verified_definitive"]
                for row in attacks
            )
            for family in FAMILIES_INCLUSION
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["signature_authenticated_false_passes"]
        == summary["attack_total"]
        == 128
        and summary["inclusion_verified_false_passes"] == 0
        and summary["inclusion_verified_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-transparency-inclusion/1",
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with OUT.open("wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0
    ) as compressed:
        compressed.write(encoded)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
