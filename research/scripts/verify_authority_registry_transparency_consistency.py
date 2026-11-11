#!/usr/bin/env python3
"""Execute the frozen transparency append-only consistency matrix."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import timedelta
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
    NOW,
    attest,
    bundle,
    chain,
    gate,
)
from verify_authority_registry_transparency_checkpoint import (
    FUTURE_SKEW_SECONDS,
    LOG_PRIVATE,
    LOG_PUBLIC,
    MAX_AGE_SECONDS,
)

from agnxiv.authority import (
    RegistryCheckpointDigestAttestationScope,
    RegistryCheckpointTransparencyCheckpoint,
    RegistryCheckpointTransparencyConsistencyWitness,
    RegistryCheckpointTransparencyInclusionWitness,
    registry_checkpoint_digest_attestation_key_sha256,
    registry_checkpoint_digest_attestation_scoped_history_commitment_sha256,
    registry_checkpoint_digest_producer_scoped_history_commitment_sha256,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
    registry_checkpoint_transparency_inclusion_witness_sha256,
    sign_registry_checkpoint_digest_attestation,
    sign_registry_checkpoint_transparency_checkpoint,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-transparency-consistency.json.gz")
SUMMARY = Path("research/results/authority-registry-transparency-consistency-summary.json")
PROVENANCE = "4" * 64
FAMILIES_CONSISTENCY = (
    "missing_prior_checkpoint",
    "non_advancing_tree",
    "rewritten_historical_prefix",
    "tampered_consistency_path",
)


def leaf_hash(statement):
    return hashlib.sha256(b"\x00" + bytes.fromhex(statement)).digest()


def node_hash(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def levels(statements):
    result = [[leaf_hash(value) for value in statements]]
    while len(result[-1]) > 1:
        row = result[-1]
        result.append([node_hash(row[i], row[i + 1]) for i in range(0, len(row), 2)])
    return result


BASE = [f"{digit:x}" * 64 for digit in range(1, 9)]
BASE[3] = PROVENANCE
APPENDED = [f"{digit:x}" * 64 for digit in range(9, 16)] + ["0" * 64]


def material(family, control):
    old_statements = list(BASE)
    new_statements = list(BASE + APPENDED)
    if family == "rewritten_historical_prefix" and not control:
        new_statements[0] = "f" * 64
    old_levels = levels(old_statements)
    new_levels = levels(new_statements)
    current_levels = new_levels
    old_size = 8
    old_root = old_levels[-1][0].hex()
    new_size = 16
    new_root = new_levels[-1][0].hex()
    consistency_path = [new_levels[3][1].hex()]
    if family == "non_advancing_tree" and not control:
        old_size = 16
        old_root = new_root
        consistency_path = []
    if family == "tampered_consistency_path" and not control:
        consistency_path = ["e" * 64]
    inclusion = RegistryCheckpointTransparencyInclusionWitness(
        log_id="agnxiv-research-log-v1",
        tree_size=16,
        leaf_index=3,
        root_sha256=new_root,
        audit_path_sha256=[
            current_levels[0][2].hex(),
            current_levels[1][0].hex(),
            current_levels[2][1].hex(),
            current_levels[3][1].hex(),
        ],
    )
    consistency = RegistryCheckpointTransparencyConsistencyWitness(
        log_id=inclusion.log_id,
        old_tree_size=old_size,
        old_root_sha256=old_root,
        new_tree_size=new_size,
        new_root_sha256=new_root,
        audit_path_sha256=consistency_path,
    )
    return old_statements, new_statements, inclusion, consistency


def signed_checkpoint(size, root, issued_at):
    checkpoint = RegistryCheckpointTransparencyCheckpoint(
        log_id="agnxiv-research-log-v1",
        tree_size=size,
        root_sha256=root,
        issued_at=issued_at,
    )
    return sign_registry_checkpoint_transparency_checkpoint(checkpoint, LOG_PRIVATE)


def run_case(case, family_index, *, control=False, negative=None):
    family = FAMILIES_CONSISTENCY[family_index]
    old_statements, new_statements, inclusion, consistency = material(family, control)
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
    scope = RegistryCheckpointDigestAttestationScope(
        predicate_type="https://slsa.dev/provenance/v1",
        provenance_statement_sha256=PROVENANCE,
        attestation_signer_key_sha256=(
            registry_checkpoint_digest_attestation_key_sha256(TRUSTED_PUBLIC)
        ),
        transparency_inclusion_witness_sha256=(
            registry_checkpoint_transparency_inclusion_witness_sha256(inclusion)
        ),
    )
    attestation_commitment = (
        registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
            producer, scope
        )
    )
    signed_attestation = sign_registry_checkpoint_digest_attestation(
        scope, TRUSTED_PRIVATE
    )
    current = signed_checkpoint(
        consistency.new_tree_size,
        consistency.new_root_sha256,
        NOW - timedelta(minutes=10),
    )
    prior = signed_checkpoint(
        consistency.old_tree_size,
        consistency.old_root_sha256,
        NOW - timedelta(minutes=20),
    )
    if family == "missing_prior_checkpoint" and not control:
        prior = None
    if negative == "missing_consistency_proof":
        consistency = None
    elif negative == "endpoint_mismatch":
        consistency = consistency.model_copy(update={"old_root_sha256": "0" * 64})
    elif negative == "invalid_prior_signature":
        prior = prior.model_copy(update={"signature_b64": "AAAA"})
    elif negative == "inconsistent_timestamp":
        prior = signed_checkpoint(
            consistency.old_tree_size,
            consistency.old_root_sha256,
            NOW - timedelta(minutes=5),
        )
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
        "signed_attestation": signed_attestation,
        "trusted_attestation_public_key_pem": TRUSTED_PUBLIC,
        "require_attestation_authentication": True,
        "transparency_inclusion_witness": inclusion,
        "require_transparency_inclusion": True,
        "signed_transparency_checkpoint": current,
        "trusted_transparency_public_key_pem": LOG_PUBLIC,
        "transparency_max_age_seconds": MAX_AGE_SECONDS,
        "transparency_future_skew_seconds": FUTURE_SKEW_SECONDS,
        "require_transparency_checkpoint": True,
    }
    parent = gate(item.model_copy(deep=True), rows, **common)
    corrected = gate(
        item.model_copy(deep=True),
        rows,
        **common,
        previous_signed_transparency_checkpoint=prior,
        transparency_consistency_witness=consistency,
        require_transparency_consistency=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "old_statements": old_statements,
        "new_statements": new_statements,
        "inclusion_witness": inclusion.model_dump(mode="json"),
        "consistency_witness": (
            None if consistency is None else consistency.model_dump(mode="json")
        ),
        "prior_checkpoint": None if prior is None else prior.model_dump(mode="json"),
        "current_checkpoint": current.model_dump(mode="json"),
        "trusted_transparency_public_key_pem": LOG_PUBLIC,
        "checkpoint_only_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "consistency_verified_definitive": (
            corrected.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "consistency_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    names = (
        "missing_consistency_proof",
        "endpoint_mismatch",
        "invalid_prior_signature",
        "inconsistent_timestamp",
    )
    return {
        name: not run_case(296000 + index, 0, control=True, negative=name)[
            "consistency_verified_definitive"
        ]
        for index, name in enumerate(names)
    }


def main():
    attacks = [
        run_case(291000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [
        run_case(295000 + offset, offset % 4, control=True) for offset in range(32)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "checkpoint_only_false_passes": sum(
            row["checkpoint_only_definitive"] for row in attacks
        ),
        "consistency_verified_false_passes": sum(
            row["consistency_verified_definitive"] for row in attacks
        ),
        "consistency_verified_controls_passed": sum(
            row["consistency_verified_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                not row["consistency_verified_definitive"]
                for row in attacks
                if row["family"] == family
            )
            for family in FAMILIES_CONSISTENCY
        },
        "negative_controls": negatives,
    }
    payload = json.dumps(
        {"attacks": attacks, "controls": controls}, sort_keys=True
    ).encode()
    with (
        OUT.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle,
    ):
        handle.write(payload)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(
        0
        if summary["checkpoint_only_false_passes"] == 128
        and summary["consistency_verified_false_passes"] == 0
        and summary["consistency_verified_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(summary["negative_controls"].values())
        else 1
    )


if __name__ == "__main__":
    main()
