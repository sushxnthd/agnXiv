#!/usr/bin/env python3
"""Execute the frozen transparency-checkpoint authentication matrix."""
from __future__ import annotations

import gzip
import json
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
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
from verify_authority_registry_checkpoint_transparency_inclusion import (
    VALID_WITNESS,
    scope_for,
)

from agnxiv.authority import (
    RegistryCheckpointTransparencyCheckpoint,
    registry_checkpoint_digest_attestation_scoped_history_commitment_sha256,
    registry_checkpoint_digest_producer_scoped_history_commitment_sha256,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
    sign_registry_checkpoint_digest_attestation,
    sign_registry_checkpoint_transparency_checkpoint,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-transparency-checkpoint.json.gz")
SUMMARY = Path("research/results/authority-registry-transparency-checkpoint-summary.json")
FAMILIES_CHECKPOINT = (
    "missing_checkpoint",
    "wrong_signing_key",
    "expired_checkpoint",
    "future_checkpoint",
)
MAX_AGE_SECONDS = 3600
FUTURE_SKEW_SECONDS = 300


def keypair(seed):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return (
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    )


LOG_PRIVATE, LOG_PUBLIC = keypair(13)
ROGUE_PRIVATE, _ = keypair(14)


def checkpoint(issued_at):
    return RegistryCheckpointTransparencyCheckpoint(
        log_id=VALID_WITNESS.log_id,
        tree_size=VALID_WITNESS.tree_size,
        root_sha256=VALID_WITNESS.root_sha256,
        issued_at=issued_at,
    )


def signed_checkpoint_for(family, control):
    if control:
        return sign_registry_checkpoint_transparency_checkpoint(
            checkpoint(NOW - timedelta(minutes=10)), LOG_PRIVATE
        )
    if family == "missing_checkpoint":
        return None
    if family == "wrong_signing_key":
        return sign_registry_checkpoint_transparency_checkpoint(
            checkpoint(NOW - timedelta(minutes=10)), ROGUE_PRIVATE
        )
    if family == "expired_checkpoint":
        return sign_registry_checkpoint_transparency_checkpoint(
            checkpoint(NOW - timedelta(hours=2)), LOG_PRIVATE
        )
    if family == "future_checkpoint":
        return sign_registry_checkpoint_transparency_checkpoint(
            checkpoint(NOW + timedelta(minutes=10)), LOG_PRIVATE
        )
    raise AssertionError(family)


def common(case, family_index):
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
    scope = scope_for(VALID_WITNESS)
    attestation_commitment = (
        registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
            producer, scope
        )
    )
    signed_attestation = sign_registry_checkpoint_digest_attestation(
        scope, TRUSTED_PRIVATE
    )
    kwargs = {
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
        "transparency_inclusion_witness": VALID_WITNESS,
        "require_transparency_inclusion": True,
    }
    return rows, item, scope, signed_attestation, kwargs


def run_case(case, family_index, *, control=False):
    family = FAMILIES_CHECKPOINT[family_index]
    rows, item, scope, signed_attestation, kwargs = common(case, family_index)
    signed_checkpoint = signed_checkpoint_for(family, control)
    parent = gate(item.model_copy(deep=True), rows, **kwargs)
    corrected = gate(
        item.model_copy(deep=True),
        rows,
        **kwargs,
        signed_transparency_checkpoint=signed_checkpoint,
        trusted_transparency_public_key_pem=LOG_PUBLIC,
        transparency_max_age_seconds=MAX_AGE_SECONDS,
        transparency_future_skew_seconds=FUTURE_SKEW_SECONDS,
        require_transparency_checkpoint=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "validation_time": NOW.isoformat(),
        "max_age_seconds": MAX_AGE_SECONDS,
        "future_skew_seconds": FUTURE_SKEW_SECONDS,
        "scope": scope.model_dump(mode="json"),
        "signed_attestation": signed_attestation.model_dump(mode="json"),
        "witness": VALID_WITNESS.model_dump(mode="json"),
        "signed_transparency_checkpoint": (
            None
            if signed_checkpoint is None
            else signed_checkpoint.model_dump(mode="json")
        ),
        "trusted_transparency_public_key_pem": LOG_PUBLIC,
        "inclusion_verified_definitive": (
            parent.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "checkpoint_verified_definitive": (
            corrected.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "checkpoint_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows, item, _, _, kwargs = common(286000, 0)
    valid = signed_checkpoint_for("missing_checkpoint", True)

    def blocked(**updates):
        options = {
            "signed_transparency_checkpoint": valid,
            "trusted_transparency_public_key_pem": LOG_PUBLIC,
            "transparency_max_age_seconds": MAX_AGE_SECONDS,
            "transparency_future_skew_seconds": FUTURE_SKEW_SECONDS,
            "require_transparency_checkpoint": True,
        }
        options.update(updates)
        call = {**kwargs, **options}
        result = gate(item.model_copy(deep=True), rows, **call)
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    mismatch = sign_registry_checkpoint_transparency_checkpoint(
        checkpoint(NOW - timedelta(minutes=10)).model_copy(
            update={"root_sha256": "f" * 64}
        ),
        LOG_PRIVATE,
    )
    return {
        "without_inclusion_mode_blocked": blocked(
            require_transparency_inclusion=False
        ),
        "missing_trusted_key_blocked": blocked(
            trusted_transparency_public_key_pem=None
        ),
        "checkpoint_witness_mismatch_blocked": blocked(
            signed_transparency_checkpoint=mismatch
        ),
        "negative_max_age_blocked": blocked(transparency_max_age_seconds=-1),
        "negative_future_skew_blocked": blocked(
            transparency_future_skew_seconds=-1
        ),
    }


def main():
    attacks = [
        run_case(281000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [
        run_case(285000 + offset, offset % 4, control=True) for offset in range(32)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "inclusion_verified_false_passes": sum(
            row["inclusion_verified_definitive"] for row in attacks
        ),
        "checkpoint_verified_false_passes": sum(
            row["checkpoint_verified_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "checkpoint_verified_controls_passed": sum(
            row["checkpoint_verified_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["checkpoint_verified_definitive"]
                for row in attacks
            )
            for family in FAMILIES_CHECKPOINT
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["inclusion_verified_false_passes"]
        == summary["attack_total"]
        == 128
        and summary["checkpoint_verified_false_passes"] == 0
        and summary["checkpoint_verified_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-transparency-checkpoint/1",
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
