#!/usr/bin/env python3
"""Execute the frozen checkpoint-history tail-truncation attack matrix."""

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
    RegistryCheckpointScope,
    authority_registry_sha256,
    registry_checkpoint_statement_sha256,
    sign_registry_checkpoint,
)
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-pinned-tip.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-pinned-tip-summary.json")


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


def gate(
    item,
    registry,
    current,
    observed,
    *,
    root_pin,
    tip_pin=None,
    require_tip=False,
    require_root=True,
):
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
        trusted_registry_checkpoint_root_statement_sha256=root_pin,
        require_registry_checkpoint_root=require_root,
        trusted_registry_checkpoint_tip_statement_sha256=tip_pin,
        require_registry_checkpoint_tip=require_tip,
    )


def chain(family):
    newest, stale = registry_pair(family)
    root = stale.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 2
    prior = stale.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH - 1
    stale.registry_epoch = CURRENT_EPOCH
    newest.registry_epoch = CURRENT_EPOCH + 1
    root_statement = statement_digest(root)
    prior_statement = statement_digest(prior)
    stale_statement = statement_digest(stale)
    root_rows = checkpoints(root)
    prior_rows = checkpoints(prior, root_statement)
    stale_rows = checkpoints(stale, prior_statement)
    newest_rows = checkpoints(newest, stale_statement)
    return {
        "root": root,
        "prior": prior,
        "stale": stale,
        "newest": newest,
        "root_statement": root_statement,
        "prior_statement": prior_statement,
        "stale_statement": stale_statement,
        "tip_statement": statement_digest(newest),
        "root_rows": root_rows,
        "prior_rows": prior_rows,
        "stale_rows": stale_rows,
        "newest_rows": newest_rows,
    }


def run_case(case, family, *, control=False):
    rows = chain(family)
    registry = rows["newest"] if control else rows["stale"]
    current = rows["newest_rows"] if control else rows["stale_rows"]
    observed = (
        [*rows["root_rows"], *rows["prior_rows"], *rows["stale_rows"]]
        if control
        else [*rows["root_rows"], *rows["prior_rows"]]
    )
    withheld = [] if control else rows["newest_rows"]
    item = bundle(case)
    attest(item, registry)
    parent = gate(
        item.model_copy(deep=True),
        registry,
        current,
        observed,
        root_pin=rows["root_statement"],
    )
    corrected = gate(
        item.model_copy(deep=True),
        registry,
        current,
        observed,
        root_pin=rows["root_statement"],
        tip_pin=rows["tip_statement"],
        require_tip=True,
    )
    reversed_result = gate(
        item.model_copy(deep=True),
        registry,
        list(reversed(current)),
        list(reversed(observed)),
        root_pin=rows["root_statement"],
        tip_pin=rows["tip_statement"],
        require_tip=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        **{
            f"{name}_registry": rows[name].model_dump(mode="json")
            for name in ("root", "prior", "stale", "newest")
        },
        **{
            f"{name}_registry_sha256": authority_registry_sha256(rows[name])
            for name in ("root", "prior", "stale", "newest")
        },
        "trusted_root_statement_sha256": rows["root_statement"],
        "prior_statement_sha256": rows["prior_statement"],
        "stale_statement_sha256": rows["stale_statement"],
        "trusted_tip_statement_sha256": rows["tip_statement"],
        "observed_checkpoints": [row.model_dump(mode="json") for row in observed],
        "current_checkpoints": [row.model_dump(mode="json") for row in current],
        "withheld_tip_checkpoints": [
            row.model_dump(mode="json") for row in withheld
        ],
        "parent_rooted_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "pinned_tip_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "reversed_order_definitive": reversed_result.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "pinned_tip_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0])
    item = bundle(195000)
    attest(item, rows["newest"])
    observed = [*rows["root_rows"], *rows["prior_rows"], *rows["stale_rows"]]

    def blocked(tip_pin, *, require_root=True):
        result = gate(
            item.model_copy(deep=True),
            rows["newest"],
            rows["newest_rows"],
            observed,
            root_pin=rows["root_statement"],
            tip_pin=tip_pin,
            require_tip=True,
            require_root=require_root,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    wrong_namespace = rows["newest"].model_copy(deep=True)
    wrong_namespace.registry_namespace = "wrong-namespace"
    wrong_epoch = rows["newest"].model_copy(deep=True)
    wrong_epoch.registry_epoch += 1
    wrong_snapshot = rows["newest"].model_copy(deep=True)
    wrong_snapshot.minimum_signatures += 1
    return {
        "missing_tip_blocked": blocked(None),
        "malformed_tip_blocked": blocked("abcd"),
        "stale_tip_blocked": blocked(rows["stale_statement"]),
        "wrong_namespace_tip_blocked": blocked(statement_digest(wrong_namespace)),
        "wrong_epoch_tip_blocked": blocked(statement_digest(wrong_epoch)),
        "wrong_snapshot_tip_blocked": blocked(statement_digest(wrong_snapshot)),
        "tip_without_root_blocked": blocked(
            rows["tip_statement"], require_root=False
        ),
    }


def main():
    attacks = [
        run_case(191000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(194000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_rooted_false_passes": sum(
            row["parent_rooted_definitive"] for row in attacks
        ),
        "pinned_tip_false_passes": sum(
            row["pinned_tip_definitive"] for row in attacks
        ),
        "reversed_order_false_passes": sum(
            row["reversed_order_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "complete_chain_controls_passed": sum(
            row["pinned_tip_definitive"] for row in controls
        ),
        "negative_controls": negatives,
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["pinned_tip_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_rooted_false_passes"] == summary["attack_total"] == 128
        and summary["pinned_tip_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["complete_chain_controls_passed"]
        == summary["control_total"]
        == 32
        and all(negatives.values())
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-pinned-tip/1",
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
