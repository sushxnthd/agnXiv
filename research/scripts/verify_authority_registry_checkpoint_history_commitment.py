#!/usr/bin/env python3
"""Execute the frozen endpoint-preserving history path-substitution matrix."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from verify_authority_registry_checkpoint_quorum import (
    CHECKPOINT_KEYS,
    CHECKPOINT_MATERIAL,
    CURRENT_EPOCH,
    NOW,
    POLICY,
    build,
    bundle,
)
from verify_authority_registry_checkpoint_snapshot import FAMILIES, attest, registry_pair

from agnxiv.authority import (
    RegistryCheckpointArtifactDigestProfile,
    RegistryCheckpointArtifactScope,
    RegistryCheckpointConsumerScope,
    RegistryCheckpointDigestAttestationScope,
    RegistryCheckpointDigestProducerScope,
    RegistryCheckpointExecutionScope,
    RegistryCheckpointScope,
    SignedRegistryCheckpointDigestAttestation,
    authority_registry_sha256,
    registry_checkpoint_linked_statement_sha256,
    registry_checkpoint_statement_sha256,
    sign_registry_checkpoint,
)
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-history-commitment.json.gz")
SUMMARY = Path(
    "research/results/authority-registry-checkpoint-history-commitment-summary.json"
)


def checkpoints(registry, previous=""):
    digest = authority_registry_sha256(registry)
    return [
        sign_registry_checkpoint(
            RegistryCheckpointScope(
                issuer=f"checkpoint-board-{index + 1}",
                key_id="monotonic-floor",
                registry_namespace=registry.registry_namespace,
                minimum_registry_epoch=registry.registry_epoch,
                authority_registry_sha256=digest,
                previous_statement_sha256=previous,
            ),
            CHECKPOINT_MATERIAL[index][0],
        )
        for index in (1, 2)
    ]


def statement_digest(registry):
    return registry_checkpoint_statement_sha256(
        registry.registry_namespace,
        registry.registry_epoch,
        authority_registry_sha256(registry),
    )


def linked_digest(registry, previous):
    return registry_checkpoint_linked_statement_sha256(
        registry.registry_namespace,
        registry.registry_epoch,
        authority_registry_sha256(registry),
        previous,
    )


def registries(family):
    final, alternate = registry_pair(family)
    root = final.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 2
    honest_mid = final.model_copy(deep=True)
    honest_mid.registry_epoch = CURRENT_EPOCH - 1
    fork_mid = alternate.model_copy(deep=True)
    fork_mid.registry_epoch = CURRENT_EPOCH - 1
    final.registry_epoch = CURRENT_EPOCH
    return root, honest_mid, fork_mid, final


def chain(family, *, recursive, fork):
    root, honest_mid, fork_mid, final = registries(family)
    middle = fork_mid if fork else honest_mid
    root_rows = checkpoints(root)
    if recursive:
        root_link = linked_digest(root, "")
        middle_rows = checkpoints(middle, root_link)
        middle_link = linked_digest(middle, root_link)
        final_rows = checkpoints(final, middle_link)
        commitment = linked_digest(final, middle_link)
    else:
        middle_rows = checkpoints(middle, statement_digest(root))
        final_rows = checkpoints(final, statement_digest(middle))
        commitment = None
    return {
        "root": root,
        "middle": middle,
        "final": final,
        "root_rows": root_rows,
        "middle_rows": middle_rows,
        "final_rows": final_rows,
        "root_pin": statement_digest(root),
        "tip_pin": statement_digest(final),
        "commitment": commitment,
    }


def gate(
    item,
    rows,
    *,
    commitment=None,
    require_commitment=False,
    consumer_scope: RegistryCheckpointConsumerScope | None = None,
    scoped_commitment=None,
    require_consumer_scope=False,
    execution_scope: RegistryCheckpointExecutionScope | None = None,
    execution_scoped_commitment=None,
    require_execution_scope=False,
    artifact_scope: RegistryCheckpointArtifactScope | None = None,
    artifact_scoped_commitment=None,
    require_artifact_scope=False,
    digest_profile: RegistryCheckpointArtifactDigestProfile | None = None,
    digest_profile_scoped_commitment=None,
    require_digest_profile=False,
    producer_scope: RegistryCheckpointDigestProducerScope | None = None,
    producer_scoped_commitment=None,
    require_producer_scope=False,
    attestation_scope: RegistryCheckpointDigestAttestationScope | None = None,
    attestation_scoped_commitment=None,
    require_attestation_scope=False,
    signed_attestation: SignedRegistryCheckpointDigestAttestation | None = None,
    trusted_attestation_public_key_pem=None,
    require_attestation_authentication=False,
    **requirements,
):
    return gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=rows["final"],
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoints=rows["final_rows"],
        observed_registry_checkpoints=[*rows["root_rows"], *rows["middle_rows"]],
        trusted_registry_checkpoint_keys=CHECKPOINT_KEYS,
        registry_checkpoint_quorum=POLICY,
        require_registry_checkpoint_quorum=True,
        require_registry_checkpoint_snapshot=True,
        require_registry_checkpoint_history=True,
        require_registry_checkpoint_chain=True,
        require_registry_checkpoint_transitive_chain=requirements.get(
            "require_transitive", True
        ),
        trusted_registry_checkpoint_root_statement_sha256=rows["root_pin"],
        require_registry_checkpoint_root=requirements.get("require_root", True),
        trusted_registry_checkpoint_tip_statement_sha256=rows["tip_pin"],
        require_registry_checkpoint_tip=requirements.get("require_tip", True),
        trusted_registry_checkpoint_history_commitment_sha256=commitment,
        require_registry_checkpoint_history_commitment=require_commitment,
        registry_checkpoint_consumer_scope=consumer_scope,
        trusted_registry_checkpoint_scoped_history_commitment_sha256=scoped_commitment,
        require_registry_checkpoint_consumer_scope=require_consumer_scope,
        registry_checkpoint_execution_scope=execution_scope,
        trusted_registry_checkpoint_execution_scoped_history_commitment_sha256=(
            execution_scoped_commitment
        ),
        require_registry_checkpoint_execution_scope=require_execution_scope,
        registry_checkpoint_artifact_scope=artifact_scope,
        trusted_registry_checkpoint_artifact_scoped_history_commitment_sha256=(
            artifact_scoped_commitment
        ),
        require_registry_checkpoint_artifact_scope=require_artifact_scope,
        registry_checkpoint_artifact_digest_profile=digest_profile,
        trusted_registry_checkpoint_digest_profile_scoped_history_commitment_sha256=(
            digest_profile_scoped_commitment
        ),
        require_registry_checkpoint_artifact_digest_profile=require_digest_profile,
        registry_checkpoint_digest_producer_scope=producer_scope,
        trusted_registry_checkpoint_digest_producer_scoped_history_commitment_sha256=(
            producer_scoped_commitment
        ),
        require_registry_checkpoint_digest_producer_scope=require_producer_scope,
        registry_checkpoint_digest_attestation_scope=attestation_scope,
        trusted_registry_checkpoint_digest_attestation_scoped_history_commitment_sha256=(
            attestation_scoped_commitment
        ),
        require_registry_checkpoint_digest_attestation_scope=(
            require_attestation_scope
        ),
        signed_registry_checkpoint_digest_attestation=signed_attestation,
        trusted_registry_checkpoint_digest_attestation_public_key_pem=(
            trusted_attestation_public_key_pem
        ),
        require_registry_checkpoint_digest_attestation_authentication=(
            require_attestation_authentication
        ),
    )


def run_case(case, family, *, control=False):
    legacy_fork = chain(family, recursive=False, fork=True)
    recursive_fork = chain(family, recursive=True, fork=True)
    recursive_honest = chain(family, recursive=True, fork=False)
    item = bundle(case)
    attest(item, recursive_honest["final"])
    parent = gate(item.model_copy(deep=True), legacy_fork)
    corrected_rows = recursive_honest if control else recursive_fork
    corrected = gate(
        item.model_copy(deep=True),
        corrected_rows,
        commitment=recursive_honest["commitment"],
        require_commitment=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "root_registry": recursive_honest["root"].model_dump(mode="json"),
        "honest_middle_registry": recursive_honest["middle"].model_dump(mode="json"),
        "fork_middle_registry": recursive_fork["middle"].model_dump(mode="json"),
        "final_registry": recursive_honest["final"].model_dump(mode="json"),
        "root_pin": recursive_honest["root_pin"],
        "tip_pin": recursive_honest["tip_pin"],
        "trusted_history_commitment": recursive_honest["commitment"],
        "fork_history_commitment": recursive_fork["commitment"],
        "legacy_fork_checkpoints": [
            row.model_dump(mode="json")
            for row in [
                *legacy_fork["root_rows"],
                *legacy_fork["middle_rows"],
                *legacy_fork["final_rows"],
            ]
        ],
        "recursive_honest_checkpoints": [
            row.model_dump(mode="json")
            for row in [
                *recursive_honest["root_rows"],
                *recursive_honest["middle_rows"],
                *recursive_honest["final_rows"],
            ]
        ],
        "recursive_fork_checkpoints": [
            row.model_dump(mode="json")
            for row in [
                *recursive_fork["root_rows"],
                *recursive_fork["middle_rows"],
                *recursive_fork["final_rows"],
            ]
        ],
        "parent_endpoint_pinning_definitive": parent.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "recursive_commitment_definitive": corrected.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "recursive_commitment_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    honest = chain(FAMILIES[0], recursive=True, fork=False)
    fork = chain(FAMILIES[0], recursive=True, fork=True)
    item = bundle(205000)
    attest(item, honest["final"])

    def blocked(commitment, **requirements):
        result = gate(
            item.model_copy(deep=True),
            honest,
            commitment=commitment,
            require_commitment=True,
            **requirements,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_commitment_blocked": blocked(None),
        "malformed_commitment_blocked": blocked("abcd"),
        "wrong_path_commitment_blocked": blocked(fork["commitment"]),
        "stale_commitment_blocked": blocked(
            linked_digest(
                honest["middle"], linked_digest(honest["root"], "")
            )
        ),
        "without_root_mode_blocked": blocked(
            honest["commitment"], require_root=False
        ),
        "without_tip_mode_blocked": blocked(honest["commitment"], require_tip=False),
        "without_transitive_mode_blocked": blocked(
            honest["commitment"], require_transitive=False
        ),
    }


def main():
    attacks = [
        run_case(201000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(204000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_endpoint_pinning_false_passes": sum(
            row["parent_endpoint_pinning_definitive"] for row in attacks
        ),
        "recursive_commitment_false_passes": sum(
            row["recursive_commitment_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "recursive_commitment_controls_passed": sum(
            row["recursive_commitment_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family
                and not row["recursive_commitment_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["parent_endpoint_pinning_false_passes"]
        == summary["attack_total"]
        == 128
        and summary["recursive_commitment_false_passes"] == 0
        and summary["recursive_commitment_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-history-commitment/1",
        "validation_time": NOW.isoformat(),
        "quorum_policy": POLICY.model_dump(mode="json"),
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with (
        OUT.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
    ):
        compressed.write(encoded)
    SUMMARY.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
