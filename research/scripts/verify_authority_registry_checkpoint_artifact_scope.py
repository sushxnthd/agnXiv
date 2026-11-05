#!/usr/bin/env python3
"""Execute the frozen same-execution cross-artifact replay matrix."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from verify_authority_registry_checkpoint_history_commitment import (
    CHECKPOINT_KEYS,
    FAMILIES,
    attest,
    bundle,
    chain,
    gate,
)

from agnxiv.authority import (
    RegistryCheckpointArtifactScope,
    RegistryCheckpointConsumerScope,
    RegistryCheckpointExecutionScope,
    registry_checkpoint_artifact_scoped_history_commitment_sha256,
    registry_checkpoint_execution_scoped_history_commitment_sha256,
    registry_checkpoint_scoped_history_commitment_sha256,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-checkpoint-artifact-scope.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-artifact-scope-summary.json")
CONSUMER = RegistryCheckpointConsumerScope(
    repository="sushxnthd/agnXiv",
    workflow_ref="production-gate.yml@refs/heads/main",
    environment="production",
)
EXECUTION = RegistryCheckpointExecutionScope(
    workflow_run_id="9400",
    workflow_run_attempt=1,
    workflow_job_id="verify",
)
ARTIFACT_FAMILIES = (
    "manuscript_substitution",
    "repository_tree_substitution",
    "claim_manifest_substitution",
    "evidence_bundle_substitution",
)


def digest(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def artifact_scope(item) -> RegistryCheckpointArtifactScope:
    return RegistryCheckpointArtifactScope(
        manuscript_sha256=item.manuscript.sha256,
        repository_tree_sha256=item.provenance.tree_digest,
        claim_manifest_sha256=digest(item.claim.model_dump(mode="json")),
        evidence_bundle_sha256=digest(
            {
                "artifacts": [row.model_dump(mode="json") for row in item.artifacts],
                "evidence_candidates": [
                    row.model_dump(mode="json") for row in item.evidence_candidates
                ],
                "execution": item.execution.model_dump(mode="json"),
            }
        ),
    )


def mutate_target(item, family, case):
    target = item.model_copy(deep=True)
    replacement = hashlib.sha256(f"target-{family}-{case}".encode()).hexdigest()
    if family == "manuscript_substitution":
        target.manuscript.sha256 = replacement
    elif family == "repository_tree_substitution":
        target.provenance.tree_digest = replacement
    elif family == "claim_manifest_substitution":
        target.claim.id = f"TARGET-{case}"
        target.record.claim.id = target.claim.id
    elif family == "evidence_bundle_substitution":
        target.execution.stdout_sha256 = replacement
    else:
        raise ValueError(f"unknown artifact family: {family}")
    return target


def envelopes(history_commitment, scope):
    consumer = registry_checkpoint_scoped_history_commitment_sha256(
        history_commitment, CONSUMER
    )
    execution = registry_checkpoint_execution_scoped_history_commitment_sha256(
        consumer, EXECUTION
    )
    artifact = registry_checkpoint_artifact_scoped_history_commitment_sha256(
        execution, scope
    )
    return consumer, execution, artifact


def run_case(case, family_index, *, control=False):
    registry_family = FAMILIES[family_index]
    family = ARTIFACT_FAMILIES[family_index]
    rows = chain(registry_family, recursive=True, fork=False)
    source_item = bundle(case)
    source_scope = artifact_scope(source_item)
    target_item = source_item if control else mutate_target(source_item, family, case)
    effective_scope = artifact_scope(target_item)
    attest(target_item, rows["final"])
    consumer, execution, artifact = envelopes(rows["commitment"], source_scope)
    parent = gate(
        target_item.model_copy(deep=True),
        rows,
        commitment=rows["commitment"],
        require_commitment=True,
        consumer_scope=CONSUMER,
        scoped_commitment=consumer,
        require_consumer_scope=True,
        execution_scope=EXECUTION,
        execution_scoped_commitment=execution,
        require_execution_scope=True,
    )
    corrected = gate(
        target_item.model_copy(deep=True),
        rows,
        commitment=rows["commitment"],
        require_commitment=True,
        consumer_scope=CONSUMER,
        scoped_commitment=consumer,
        require_consumer_scope=True,
        execution_scope=EXECUTION,
        execution_scoped_commitment=execution,
        require_execution_scope=True,
        artifact_scope=effective_scope,
        artifact_scoped_commitment=artifact,
        require_artifact_scope=True,
    )
    return {
        "case": case,
        "artifact_family": family,
        "registry_family": registry_family,
        "control": control,
        "registries": [
            rows[name].model_dump(mode="json") for name in ("root", "middle", "final")
        ],
        "checkpoints": [
            row.model_dump(mode="json")
            for row in [
                *rows["root_rows"],
                *rows["middle_rows"],
                *rows["final_rows"],
            ]
        ],
        "consumer_scope": CONSUMER.model_dump(mode="json"),
        "execution_scope": EXECUTION.model_dump(mode="json"),
        "source_artifact_scope": source_scope.model_dump(mode="json"),
        "effective_artifact_scope": effective_scope.model_dump(mode="json"),
        "history_commitment": rows["commitment"],
        "trusted_consumer_commitment": consumer,
        "trusted_execution_commitment": execution,
        "trusted_artifact_commitment": artifact,
        "execution_scoped_commitment_definitive": (
            parent.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "artifact_scoped_commitment_definitive": (
            corrected.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "artifact_scope_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(236000)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True),
            rows,
            commitment=rows["commitment"],
            require_commitment=True,
            consumer_scope=CONSUMER,
            scoped_commitment=consumer,
            require_consumer_scope=True,
            execution_scope=EXECUTION,
            execution_scoped_commitment=overrides.get("execution", execution),
            require_execution_scope=overrides.get("require_execution", True),
            artifact_scope=overrides.get("scope", scope),
            artifact_scoped_commitment=overrides.get("artifact", artifact),
            require_artifact_scope=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_artifact_scope_blocked": blocked(scope=None),
        "missing_artifact_commitment_blocked": blocked(artifact=None),
        "malformed_artifact_commitment_blocked": blocked(artifact="abcd"),
        "without_execution_mode_blocked": blocked(require_execution=False),
        "wrong_manuscript_blocked": blocked(
            scope=scope.model_copy(update={"manuscript_sha256": "a" * 64})
        ),
        "wrong_tree_blocked": blocked(
            scope=scope.model_copy(update={"repository_tree_sha256": "b" * 64})
        ),
        "wrong_claim_manifest_blocked": blocked(
            scope=scope.model_copy(update={"claim_manifest_sha256": "c" * 64})
        ),
        "wrong_evidence_bundle_blocked": blocked(
            scope=scope.model_copy(update={"evidence_bundle_sha256": "d" * 64})
        ),
    }


def main():
    attacks = [
        run_case(231000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [run_case(235000 + offset, offset % 4, control=True) for offset in range(32)]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "execution_scoped_false_passes": sum(
            row["execution_scoped_commitment_definitive"] for row in attacks
        ),
        "artifact_scoped_false_passes": sum(
            row["artifact_scoped_commitment_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "artifact_scoped_controls_passed": sum(
            row["artifact_scoped_commitment_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["artifact_family"] == family
                and not row["artifact_scoped_commitment_definitive"]
                for row in attacks
            )
            for family in ARTIFACT_FAMILIES
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["execution_scoped_false_passes"] == summary["attack_total"] == 128
        and summary["artifact_scoped_false_passes"] == 0
        and summary["artifact_scoped_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-artifact-scope/1",
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
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
    SUMMARY.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()