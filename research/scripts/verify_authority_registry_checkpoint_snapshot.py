#!/usr/bin/env python3
"""Execute the frozen same-epoch registry-fork matrix."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from verify_authority_registry_checkpoint_quorum import (
    CHECKPOINT_KEYS,
    CHECKPOINT_MATERIAL,
    CURRENT_EPOCH,
    NOW,
    POLICY,
    build,
    bundle,
    credential,
)

from agnxiv.authority import (
    RegistryCheckpointScope,
    TrustedAuthorityKey,
    TrustedAuthorityRegistry,
    authority_registry_sha256,
    authority_scope_for_bundle,
    sign_authority_scope,
    sign_registry_checkpoint,
)
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-snapshot.json")
FAMILIES = ("revocation", "trust_domain", "quorum", "key_set")
AUTHORITY_MATERIAL = tuple(credential(seed) for seed in (61, 62, 63, 64))


def registry_pair(family: str):
    base_keys = [
        TrustedAuthorityKey(
            issuer="review-board-a",
            key_id="primary",
            public_key_pem=AUTHORITY_MATERIAL[0][1],
            trust_domain="review-operator-a",
        ),
        TrustedAuthorityKey(
            issuer="review-board-b",
            key_id="primary",
            public_key_pem=AUTHORITY_MATERIAL[1][1],
            trust_domain="review-operator-b",
        ),
    ]
    legitimate = TrustedAuthorityRegistry(
        registry_namespace="production-release",
        registry_epoch=CURRENT_EPOCH,
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=base_keys,
    )
    fork = legitimate.model_copy(deep=True)
    if family == "revocation":
        legitimate.keys.append(
            TrustedAuthorityKey(
                issuer="retired-reviewer",
                key_id="secondary",
                public_key_pem=AUTHORITY_MATERIAL[2][1],
                trust_domain="retired-operator",
                status="revoked",
            )
        )
        fork = legitimate.model_copy(deep=True)
        fork.keys[-1].status = "active"
    elif family == "trust_domain":
        fork.keys[1].trust_domain = "forked-review-operator"
    elif family == "quorum":
        fork.minimum_signatures = 1
    elif family == "key_set":
        legitimate.keys.append(
            TrustedAuthorityKey(
                issuer="canonical-auditor",
                key_id="secondary",
                public_key_pem=AUTHORITY_MATERIAL[2][1],
                trust_domain="audit-operator",
            )
        )
        fork.keys.append(
            TrustedAuthorityKey(
                issuer="substituted-auditor",
                key_id="secondary",
                public_key_pem=AUTHORITY_MATERIAL[3][1],
                trust_domain="audit-operator",
            )
        )
    else:  # pragma: no cover - frozen family set
        raise ValueError(family)
    return legitimate, fork


def attest(item, registry):
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=registry,
                issuer=f"review-board-{letter}",
                key_id="primary",
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(days=1),
            ),
            AUTHORITY_MATERIAL[index][0],
        )
        for index, letter in enumerate(("a", "b"))
    ]


def checkpoints(registry):
    digest = authority_registry_sha256(registry)
    return [
        sign_registry_checkpoint(
            RegistryCheckpointScope(
                issuer=f"checkpoint-board-{index + 1}",
                key_id="monotonic-floor",
                registry_namespace=registry.registry_namespace,
                minimum_registry_epoch=registry.registry_epoch,
                authority_registry_sha256=digest,
            ),
            CHECKPOINT_MATERIAL[index][0],
        )
        for index in (1, 2)
    ]


def gate(item, registry, signed, *, snapshot):
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
        require_registry_checkpoint_snapshot=snapshot,
    )


def run_case(case: int, family: str, *, control: bool = False):
    legitimate, fork = registry_pair(family)
    supplied_registry = legitimate if control else fork
    item = bundle(case)
    attest(item, supplied_registry)
    signed = checkpoints(legitimate)
    parent = gate(item.model_copy(deep=True), supplied_registry, signed, snapshot=False)
    corrected = gate(item.model_copy(deep=True), supplied_registry, signed, snapshot=True)
    return {
        "case": case,
        "family": family,
        "control": control,
        "endorsed_registry": legitimate.model_dump(mode="json"),
        "supplied_registry": supplied_registry.model_dump(mode="json"),
        "endorsed_registry_sha256": authority_registry_sha256(legitimate),
        "supplied_registry_sha256": authority_registry_sha256(supplied_registry),
        "supplied_checkpoints": [row.model_dump(mode="json") for row in signed],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "snapshot_bound_definitive": corrected.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "snapshot_bound_reasons": corrected.verdict_gate_reasons,
    }


def main():
    attacks = [
        run_case(80000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(90000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "snapshot_bound_false_passes": sum(
            row["snapshot_bound_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "snapshot_bound_controls_passed": sum(
            row["snapshot_bound_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["snapshot_bound_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["snapshot_bound_false_passes"] == 0
        and summary["snapshot_bound_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-snapshot/1",
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
