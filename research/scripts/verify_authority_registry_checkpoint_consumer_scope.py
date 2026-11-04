#!/usr/bin/env python3
"""Execute the frozen cross-consumer recursive-commitment replay matrix."""

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
    registry_checkpoint_scoped_history_commitment_sha256,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-checkpoint-consumer-scope.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-consumer-scope-summary.json")
SCOPE_FAMILIES = (
    (
        "staging_to_production",
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="staging.yml@refs/heads/main", environment="staging"),
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="production.yml@refs/heads/main", environment="production"),
    ),
    (
        "tenant_to_tenant",
        RegistryCheckpointConsumerScope(repository="tenant-a/paper-audit", workflow_ref="verify.yml@refs/heads/main", environment="production"),
        RegistryCheckpointConsumerScope(repository="tenant-b/paper-audit", workflow_ref="verify.yml@refs/heads/main", environment="production"),
    ),
    (
        "paper_review_to_release",
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="paper-review.yml@refs/heads/main", environment="review"),
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="release.yml@refs/heads/main", environment="release"),
    ),
    (
        "benchmark_to_external_audit",
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="benchmark.yml@refs/heads/main", environment="benchmark"),
        RegistryCheckpointConsumerScope(repository="sushxnthd/agnXiv", workflow_ref="external-audit.yml@refs/heads/main", environment="external-audit"),
    ),
)


def envelope(commitment, scope):
    return registry_checkpoint_scoped_history_commitment_sha256(commitment, scope)


def run_case(case, family_index, *, control=False):
    registry_family = FAMILIES[family_index]
    scope_family, source_scope, target_scope = SCOPE_FAMILIES[family_index]
    rows = chain(registry_family, recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    trusted_envelope = envelope(rows["commitment"], source_scope)
    effective_scope = source_scope if control else target_scope
    parent = gate(item.model_copy(deep=True), rows, commitment=rows["commitment"], require_commitment=True)
    corrected = gate(
        item.model_copy(deep=True), rows,
        commitment=rows["commitment"], require_commitment=True,
        consumer_scope=effective_scope, scoped_commitment=trusted_envelope,
        require_consumer_scope=True,
    )
    return {
        "case": case,
        "scope_family": scope_family,
        "registry_family": registry_family,
        "control": control,
        "registries": [rows[name].model_dump(mode="json") for name in ("root", "middle", "final")],
        "checkpoints": [row.model_dump(mode="json") for row in [*rows["root_rows"], *rows["middle_rows"], *rows["final_rows"]]],
        "source_scope": source_scope.model_dump(mode="json"),
        "effective_scope": effective_scope.model_dump(mode="json"),
        "history_commitment": rows["commitment"],
        "trusted_scoped_commitment": trusted_envelope,
        "parent_recursive_commitment_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "consumer_scoped_commitment_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "consumer_scope_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(216000)
    attest(item, rows["final"])
    scope = SCOPE_FAMILIES[0][1]
    trusted = envelope(rows["commitment"], scope)

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True), rows,
            commitment=rows["commitment"],
            require_commitment=overrides.get("require_commitment", True),
            consumer_scope=overrides.get("consumer_scope", scope),
            scoped_commitment=overrides.get("scoped_commitment", trusted),
            require_consumer_scope=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_scope_blocked": blocked(consumer_scope=None),
        "missing_envelope_blocked": blocked(scoped_commitment=None),
        "malformed_envelope_blocked": blocked(scoped_commitment="abcd"),
        "without_history_mode_blocked": blocked(require_commitment=False),
        "wrong_repository_blocked": blocked(consumer_scope=scope.model_copy(update={"repository": "attacker/repo"})),
        "wrong_workflow_blocked": blocked(consumer_scope=scope.model_copy(update={"workflow_ref": "other.yml@main"})),
        "wrong_environment_blocked": blocked(consumer_scope=scope.model_copy(update={"environment": "development"})),
    }


def main():
    attacks = [run_case(211000 + 100 * family + offset, family) for family in range(4) for offset in range(32)]
    controls = [run_case(215000 + offset, offset % 4, control=True) for offset in range(32)]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_recursive_commitment_false_passes": sum(row["parent_recursive_commitment_definitive"] for row in attacks),
        "consumer_scoped_false_passes": sum(row["consumer_scoped_commitment_definitive"] for row in attacks),
        "control_total": len(controls),
        "consumer_scoped_controls_passed": sum(row["consumer_scoped_commitment_definitive"] for row in controls),
        "families_blocked": {name: sum(row["scope_family"] == name and not row["consumer_scoped_commitment_definitive"] for row in attacks) for name, _, _ in SCOPE_FAMILIES},
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["parent_recursive_commitment_false_passes"] == summary["attack_total"] == 128
        and summary["consumer_scoped_false_passes"] == 0
        and summary["consumer_scoped_controls_passed"] == summary["control_total"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-consumer-scope/1",
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
        "attacks": attacks, "controls": controls, "summary": summary,
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
