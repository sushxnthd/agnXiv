#!/usr/bin/env python3
"""Execute the frozen disclosed checkpoint-equivocation matrix."""

from __future__ import annotations

import json
from pathlib import Path

from verify_authority_registry_checkpoint_quorum import (
    CHECKPOINT_KEYS,
    NOW,
    POLICY,
    build,
    bundle,
)
from verify_authority_registry_checkpoint_snapshot import (
    FAMILIES,
    attest,
    checkpoints,
    registry_pair,
)

from agnxiv.authority import authority_registry_sha256
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-equivocation.json")


def legacy_snapshot_selection(signed, supplied_registry):
    """Reproduce the frozen parent selection over already valid 2-of-2 quorums."""
    statements = []
    for offset in range(0, len(signed), 2):
        pair = signed[offset : offset + 2]
        scopes = [row.scope for row in pair]
        statement = (
            scopes[0].registry_namespace,
            scopes[0].minimum_registry_epoch,
            scopes[0].authority_registry_sha256,
        )
        if len(scopes) == 2 and all(
            (
                scope.registry_namespace,
                scope.minimum_registry_epoch,
                scope.authority_registry_sha256,
            )
            == statement
            for scope in scopes
        ):
            statements.append(statement)
    if not statements:
        return False
    namespace = statements[0][0]
    floor = max(epoch for candidate, epoch, _ in statements if candidate == namespace)
    selected = next(
        digest
        for candidate, epoch, digest in statements
        if candidate == namespace and epoch == floor
    )
    return (
        namespace == supplied_registry.registry_namespace
        and supplied_registry.registry_epoch >= floor
        and selected == authority_registry_sha256(supplied_registry)
    )


def gate(item, registry, signed):
    return gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoints=signed,
        trusted_registry_checkpoint_keys=CHECKPOINT_KEYS,
        registry_checkpoint_quorum=POLICY,
        require_registry_checkpoint_quorum=True,
        require_registry_checkpoint_snapshot=True,
    )


def run_case(case, family, *, control=False):
    legitimate, fork = registry_pair(family)
    item = bundle(case)
    attest(item, legitimate)
    target = checkpoints(legitimate)
    conflicting = [] if control else checkpoints(fork)
    signed = target + conflicting
    corrected = gate(item.model_copy(deep=True), legitimate, signed)
    reversed_result = gate(
        item.model_copy(deep=True), legitimate, list(reversed(signed))
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "supplied_registry": legitimate.model_dump(mode="json"),
        "conflicting_registry": None if control else fork.model_dump(mode="json"),
        "supplied_registry_sha256": authority_registry_sha256(legitimate),
        "conflicting_registry_sha256": (
            None if control else authority_registry_sha256(fork)
        ),
        "supplied_checkpoints": [row.model_dump(mode="json") for row in signed],
        "parent_snapshot_definitive": legacy_snapshot_selection(signed, legitimate),
        "equivocation_bound_definitive": (
            corrected.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "reversed_order_definitive": (
            reversed_result.record.verdict != Verdict.UNABLE_TO_VERIFY
        ),
        "equivocation_reasons": corrected.verdict_gate_reasons,
    }


def main():
    attacks = [
        run_case(100000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(110000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_snapshot_definitive"] for row in attacks),
        "equivocation_bound_false_passes": sum(
            row["equivocation_bound_definitive"] for row in attacks
        ),
        "reversed_order_false_passes": sum(
            row["reversed_order_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "controls_passed": sum(
            row["equivocation_bound_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family
                and not row["equivocation_bound_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["equivocation_bound_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["controls_passed"] == summary["control_total"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-equivocation/1",
        "validation_time": NOW.isoformat(),
        "quorum_policy": POLICY.model_dump(mode="json"),
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
