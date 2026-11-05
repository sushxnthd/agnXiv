#!/usr/bin/env python3
"""Execute the frozen digest-producer substitution matrix."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from verify_authority_registry_checkpoint_artifact_scope import (
    CONSUMER,
    EXECUTION,
    artifact_scope,
    envelopes,
)
from verify_authority_registry_checkpoint_digest_profile import TRUSTED as PROFILE
from verify_authority_registry_checkpoint_history_commitment import (
    FAMILIES,
    attest,
    bundle,
    chain,
    gate,
)

from agnxiv.authority import (
    RegistryCheckpointDigestProducerScope,
    registry_checkpoint_digest_producer_scoped_history_commitment_sha256,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-checkpoint-digest-producer.json.gz")
SUMMARY = Path(
    "research/results/authority-registry-checkpoint-digest-producer-summary.json"
)
TRUSTED = RegistryCheckpointDigestProducerScope(
    producer_id="agnxiv-digest-producer",
    implementation_sha256="1" * 64,
    runtime_image_digest="sha256:" + "2" * 64,
    toolchain_manifest_sha256="3" * 64,
)
ATTACKS = (
    ("producer_identity", "producer_id", "replacement-digest-producer"),
    ("producer_implementation", "implementation_sha256", "4" * 64),
    ("producer_runtime_image", "runtime_image_digest", "sha256:" + "5" * 64),
    ("producer_toolchain", "toolchain_manifest_sha256", "6" * 64),
)


def run_case(case, family_index, *, control=False):
    name, field, replacement = ATTACKS[family_index]
    rows = chain(FAMILIES[family_index], recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact, PROFILE
    )
    trusted_producer = (
        registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
            profile, TRUSTED
        )
    )
    effective = TRUSTED if control else TRUSTED.model_copy(update={field: replacement})
    common = {
        "commitment": rows["commitment"],
        "require_commitment": True,
        "consumer_scope": CONSUMER,
        "scoped_commitment": consumer,
        "require_consumer_scope": True,
        "execution_scope": EXECUTION,
        "execution_scoped_commitment": execution,
        "require_execution_scope": True,
        "artifact_scope": scope,
        "artifact_scoped_commitment": artifact,
        "require_artifact_scope": True,
        "digest_profile": PROFILE,
        "digest_profile_scoped_commitment": profile,
        "require_digest_profile": True,
    }
    parent = gate(item.model_copy(deep=True), rows, **common)
    corrected = gate(
        item.model_copy(deep=True), rows, **common,
        producer_scope=effective,
        producer_scoped_commitment=trusted_producer,
        require_producer_scope=True,
    )
    return {
        "case": case,
        "family": name,
        "control": control,
        "profile_commitment": profile,
        "source_producer": TRUSTED.model_dump(mode="json"),
        "effective_producer": effective.model_dump(mode="json"),
        "trusted_producer_commitment": trusted_producer,
        "profile_scoped_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "producer_scoped_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "producer_scope_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(256000)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact, PROFILE
    )
    producer = registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
        profile, TRUSTED
    )

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True), rows,
            commitment=rows["commitment"], require_commitment=True,
            consumer_scope=CONSUMER, scoped_commitment=consumer,
            require_consumer_scope=True,
            execution_scope=EXECUTION, execution_scoped_commitment=execution,
            require_execution_scope=True,
            artifact_scope=scope, artifact_scoped_commitment=artifact,
            require_artifact_scope=True,
            digest_profile=PROFILE, digest_profile_scoped_commitment=profile,
            require_digest_profile=overrides.get("require_profile", True),
            producer_scope=overrides.get("scope", TRUSTED),
            producer_scoped_commitment=overrides.get("commitment", producer),
            require_producer_scope=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_scope_blocked": blocked(scope=None),
        "missing_commitment_blocked": blocked(commitment=None),
        "malformed_commitment_blocked": blocked(commitment="abcd"),
        "without_profile_mode_blocked": blocked(require_profile=False),
        **{
            f"wrong_{field}_blocked": blocked(
                scope=TRUSTED.model_copy(update={field: value})
            )
            for _, field, value in ATTACKS
        },
    }


def main():
    attacks = [
        run_case(251000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [
        run_case(255000 + offset, offset % 4, control=True) for offset in range(32)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "profile_scoped_false_passes": sum(
            row["profile_scoped_definitive"] for row in attacks
        ),
        "producer_scoped_false_passes": sum(
            row["producer_scoped_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "producer_scoped_controls_passed": sum(
            row["producer_scoped_definitive"] for row in controls
        ),
        "families_blocked": {
            name: sum(
                row["family"] == name and not row["producer_scoped_definitive"]
                for row in attacks
            )
            for name, _, _ in ATTACKS
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["profile_scoped_false_passes"] == summary["attack_total"] == 128
        and summary["producer_scoped_false_passes"] == 0
        and summary["producer_scoped_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-digest-producer/1",
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
