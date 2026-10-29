#!/usr/bin/env python3
"""Execute the frozen checkpoint-history prefix-truncation attack matrix."""

from __future__ import annotations

import gzip
import hashlib
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
    RegistryCheckpointScope,
    authority_registry_sha256,
    registry_checkpoint_statement_sha256,
    sign_registry_checkpoint,
)
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-pinned-root.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-pinned-root-summary.json")


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


def gate(item, registry, current, observed, *, pin=None, require_root=False):
    return gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoints=current,
        observed_registry_checkpoints=observed,
        trusted_registry_checkpoint_keys=CHECKPOINT_KEYS,
        registry_checkpoint_quorum=POLICY,
        require_registry_checkpoint_quorum=True,
        require_registry_checkpoint_snapshot=True,
        require_registry_checkpoint_history=True,
        require_registry_checkpoint_chain=True,
        require_registry_checkpoint_transitive_chain=True,
        trusted_registry_checkpoint_root_statement_sha256=pin,
        require_registry_checkpoint_root=require_root,
    )


def run_case(case, family, *, control=False):
    legitimate, fork = registry_pair(family)
    root = legitimate.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 1
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    current_registry = (legitimate if control else fork).model_copy(deep=True)
    current_registry.registry_epoch = CURRENT_EPOCH + 1
    root_statement = statement_digest(root)
    prior_statement = statement_digest(prior)
    full_history = [
        *checkpoints(root),
        *checkpoints(prior, root_statement),
    ]
    supplied_history = full_history if control else full_history[2:]
    current = checkpoints(current_registry, prior_statement)
    item = bundle(case)
    attest(item, current_registry)
    parent = gate(
        item.model_copy(deep=True), current_registry, current, supplied_history
    )
    corrected = gate(
        item.model_copy(deep=True),
        current_registry,
        current,
        supplied_history,
        pin=root_statement,
        require_root=True,
    )
    reversed_result = gate(
        item.model_copy(deep=True),
        current_registry,
        list(reversed(current)),
        list(reversed(supplied_history)),
        pin=root_statement,
        require_root=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "root_registry": root.model_dump(mode="json"),
        "prior_registry": prior.model_dump(mode="json"),
        "current_registry": current_registry.model_dump(mode="json"),
        "root_registry_sha256": authority_registry_sha256(root),
        "prior_registry_sha256": authority_registry_sha256(prior),
        "current_registry_sha256": authority_registry_sha256(current_registry),
        "trusted_root_statement_sha256": root_statement,
        "prior_statement_sha256": prior_statement,
        "supplied_history_starts_at": "root" if control else "prior",
        "observed_checkpoints": [row.model_dump(mode="json") for row in supplied_history],
        "current_checkpoints": [row.model_dump(mode="json") for row in current],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "pinned_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "reversed_order_definitive": reversed_result.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "pinned_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    legitimate, _ = registry_pair(FAMILIES[0])
    root = legitimate.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 1
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    current = legitimate.model_copy(deep=True)
    current.registry_epoch = CURRENT_EPOCH + 1
    root_statement = statement_digest(root)
    observed = [*checkpoints(root), *checkpoints(prior, root_statement)]
    current_rows = checkpoints(current, statement_digest(prior))
    item = bundle(185000)
    attest(item, current)

    def blocked(pin):
        result = gate(
            item.model_copy(deep=True),
            current,
            current_rows,
            observed,
            pin=pin,
            require_root=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_pin_blocked": blocked(None),
        "malformed_pin_blocked": blocked("abcd"),
        "wrong_namespace_pin_blocked": blocked(
            hashlib.sha256(b"wrong-namespace-root").hexdigest()
        ),
        "wrong_epoch_pin_blocked": blocked(statement_digest(prior)),
        "wrong_snapshot_pin_blocked": blocked("0" * 64),
    }


def main():
    attacks = [
        run_case(181000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(184000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "pinned_root_false_passes": sum(
            row["pinned_definitive"] for row in attacks
        ),
        "reversed_order_false_passes": sum(
            row["reversed_order_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "complete_history_controls_passed": sum(
            row["pinned_definitive"] for row in controls
        ),
        "negative_controls": negatives,
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["pinned_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["pinned_root_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["complete_history_controls_passed"]
        == summary["control_total"]
        == 32
        and all(negatives.values())
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-pinned-root/1",
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
