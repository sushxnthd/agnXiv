#!/usr/bin/env python3
"""Execute the frozen same-consumer cross-execution replay matrix."""

from __future__ import annotations

import gzip
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
    RegistryCheckpointConsumerScope,
    RegistryCheckpointExecutionScope,
    registry_checkpoint_execution_scoped_history_commitment_sha256,
    registry_checkpoint_scoped_history_commitment_sha256,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-checkpoint-execution-scope.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-execution-scope-summary.json")
CONSUMER = RegistryCheckpointConsumerScope(
    repository="sushxnthd/agnXiv",
    workflow_ref="production-gate.yml@refs/heads/main",
    environment="production",
)
EXECUTION_FAMILIES = (
    (
        "run_to_run",
        RegistryCheckpointExecutionScope(workflow_run_id="9001", workflow_run_attempt=1, workflow_job_id="verify"),
        RegistryCheckpointExecutionScope(workflow_run_id="9002", workflow_run_attempt=1, workflow_job_id="verify"),
    ),
    (
        "attempt_to_retry",
        RegistryCheckpointExecutionScope(workflow_run_id="9100", workflow_run_attempt=1, workflow_job_id="verify"),
        RegistryCheckpointExecutionScope(workflow_run_id="9100", workflow_run_attempt=2, workflow_job_id="verify"),
    ),
    (
        "job_to_job",
        RegistryCheckpointExecutionScope(workflow_run_id="9200", workflow_run_attempt=1, workflow_job_id="verify"),
        RegistryCheckpointExecutionScope(workflow_run_id="9200", workflow_run_attempt=1, workflow_job_id="publish"),
    ),
    (
        "matrix_shard_to_shard",
        RegistryCheckpointExecutionScope(workflow_run_id="9300", workflow_run_attempt=1, workflow_job_id="verify-py311"),
        RegistryCheckpointExecutionScope(workflow_run_id="9300", workflow_run_attempt=1, workflow_job_id="verify-py312"),
    ),
)


def envelopes(history_commitment, execution_scope):
    consumer = registry_checkpoint_scoped_history_commitment_sha256(
        history_commitment, CONSUMER
    )
    execution = registry_checkpoint_execution_scoped_history_commitment_sha256(
        consumer, execution_scope
    )
    return consumer, execution


def run_case(case, family_index, *, control=False):
    registry_family = FAMILIES[family_index]
    execution_family, source_execution, target_execution = EXECUTION_FAMILIES[family_index]
    rows = chain(registry_family, recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    consumer_envelope, execution_envelope = envelopes(
        rows["commitment"], source_execution
    )
    effective_execution = source_execution if control else target_execution
    parent = gate(
        item.model_copy(deep=True), rows,
        commitment=rows["commitment"], require_commitment=True,
        consumer_scope=CONSUMER, scoped_commitment=consumer_envelope,
        require_consumer_scope=True,
    )
    corrected = gate(
        item.model_copy(deep=True), rows,
        commitment=rows["commitment"], require_commitment=True,
        consumer_scope=CONSUMER, scoped_commitment=consumer_envelope,
        require_consumer_scope=True,
        execution_scope=effective_execution,
        execution_scoped_commitment=execution_envelope,
        require_execution_scope=True,
    )
    return {
        "case": case,
        "execution_family": execution_family,
        "registry_family": registry_family,
        "control": control,
        "registries": [rows[name].model_dump(mode="json") for name in ("root", "middle", "final")],
        "checkpoints": [row.model_dump(mode="json") for row in [*rows["root_rows"], *rows["middle_rows"], *rows["final_rows"]]],
        "consumer_scope": CONSUMER.model_dump(mode="json"),
        "source_execution_scope": source_execution.model_dump(mode="json"),
        "effective_execution_scope": effective_execution.model_dump(mode="json"),
        "history_commitment": rows["commitment"],
        "trusted_consumer_commitment": consumer_envelope,
        "trusted_execution_commitment": execution_envelope,
        "consumer_scoped_commitment_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "execution_scoped_commitment_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "execution_scope_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(226000)
    attest(item, rows["final"])
    execution = EXECUTION_FAMILIES[0][1]
    consumer_envelope, execution_envelope = envelopes(rows["commitment"], execution)

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True), rows,
            commitment=rows["commitment"], require_commitment=True,
            consumer_scope=CONSUMER,
            scoped_commitment=overrides.get("consumer_envelope", consumer_envelope),
            require_consumer_scope=overrides.get("require_consumer_scope", True),
            execution_scope=overrides.get("execution_scope", execution),
            execution_scoped_commitment=overrides.get("execution_envelope", execution_envelope),
            require_execution_scope=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_execution_scope_blocked": blocked(execution_scope=None),
        "missing_execution_envelope_blocked": blocked(execution_envelope=None),
        "malformed_execution_envelope_blocked": blocked(execution_envelope="abcd"),
        "without_consumer_mode_blocked": blocked(require_consumer_scope=False),
        "wrong_run_blocked": blocked(execution_scope=execution.model_copy(update={"workflow_run_id": "other"})),
        "wrong_attempt_blocked": blocked(execution_scope=execution.model_copy(update={"workflow_run_attempt": 2})),
        "wrong_job_blocked": blocked(execution_scope=execution.model_copy(update={"workflow_job_id": "other"})),
    }


def main():
    attacks = [run_case(221000 + 100 * family + offset, family) for family in range(4) for offset in range(32)]
    controls = [run_case(225000 + offset, offset % 4, control=True) for offset in range(32)]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "consumer_scoped_false_passes": sum(row["consumer_scoped_commitment_definitive"] for row in attacks),
        "execution_scoped_false_passes": sum(row["execution_scoped_commitment_definitive"] for row in attacks),
        "control_total": len(controls),
        "execution_scoped_controls_passed": sum(row["execution_scoped_commitment_definitive"] for row in controls),
        "families_blocked": {name: sum(row["execution_family"] == name and not row["execution_scoped_commitment_definitive"] for row in attacks) for name, _, _ in EXECUTION_FAMILIES},
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["consumer_scoped_false_passes"] == summary["attack_total"] == 128
        and summary["execution_scoped_false_passes"] == 0
        and summary["execution_scoped_controls_passed"] == summary["control_total"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-execution-scope/1",
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with OUT.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        compressed.write(encoded)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
