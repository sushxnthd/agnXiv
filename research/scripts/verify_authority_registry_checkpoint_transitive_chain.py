#!/usr/bin/env python3
"""Execute the frozen detached checkpoint-history-prefix attack matrix."""

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

OUT = Path("research/results/authority-registry-checkpoint-transitive-chain.json.gz")
SUMMARY = Path(
    "research/results/authority-registry-checkpoint-transitive-chain-summary.json"
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


def gate(item, registry, current, observed, *, transitive):
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
        require_registry_checkpoint_transitive_chain=transitive,
    )


def run_case(case, family, *, control=False):
    legitimate, fork = registry_pair(family)
    root = legitimate.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 1
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    current_registry = (legitimate if control else fork).model_copy(deep=True)
    current_registry.registry_epoch = CURRENT_EPOCH + 1
    root_link = statement_digest(root)
    supplied_prior_link = (
        root_link
        if control
        else hashlib.sha256(f"detached-prefix:{case}:{family}".encode()).hexdigest()
    )
    observed = [
        *checkpoints(root),
        *checkpoints(prior, supplied_prior_link),
    ]
    current = checkpoints(current_registry, statement_digest(prior))
    item = bundle(case)
    attest(item, current_registry)
    parent = gate(
        item.model_copy(deep=True), current_registry, current, observed, transitive=False
    )
    corrected = gate(
        item.model_copy(deep=True), current_registry, current, observed, transitive=True
    )
    reversed_result = gate(
        item.model_copy(deep=True),
        current_registry,
        list(reversed(current)),
        list(reversed(observed)),
        transitive=True,
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
        "expected_prior_link_sha256": root_link,
        "supplied_prior_link_sha256": supplied_prior_link,
        "expected_current_link_sha256": statement_digest(prior),
        "observed_checkpoints": [row.model_dump(mode="json") for row in observed],
        "current_checkpoints": [row.model_dump(mode="json") for row in current],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "transitive_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "reversed_order_definitive": reversed_result.record.verdict
        != Verdict.UNABLE_TO_VERIFY,
        "transitive_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    legitimate, _ = registry_pair(FAMILIES[0])
    root = legitimate.model_copy(deep=True)
    root.registry_epoch = CURRENT_EPOCH - 2
    middle = legitimate.model_copy(deep=True)
    middle.registry_epoch = CURRENT_EPOCH - 1
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    current = legitimate.model_copy(deep=True)
    current.registry_epoch = CURRENT_EPOCH + 1
    item = bundle(180000)
    attest(item, current)

    def blocked(observed):
        result = gate(
            item.model_copy(deep=True),
            current,
            checkpoints(current, statement_digest(prior)),
            observed,
            transitive=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    correct_root = checkpoints(root)
    missing = [*correct_root, *checkpoints(prior)]
    malformed = [*correct_root, *checkpoints(prior, "abcd")]
    mixed = [
        *correct_root,
        checkpoints(prior, statement_digest(root))[0],
        checkpoints(prior, "0" * 64)[1],
    ]
    skipped = [
        *correct_root,
        *checkpoints(middle, statement_digest(root)),
        *checkpoints(prior, statement_digest(root)),
    ]
    backward = [
        *correct_root,
        *checkpoints(prior, hashlib.sha256(b"future-statement").hexdigest()),
    ]
    return {
        "missing_historical_link_blocked": blocked(missing),
        "malformed_historical_link_blocked": blocked(malformed),
        "mixed_historical_links_blocked": blocked(mixed),
        "skipped_historical_link_blocked": blocked(skipped),
        "backward_unknown_link_blocked": blocked(backward),
    }


def main():
    attacks = [
        run_case(175000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(179000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "transitive_false_passes": sum(
            row["transitive_definitive"] for row in attacks
        ),
        "reversed_order_false_passes": sum(
            row["reversed_order_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "linked_controls_passed": sum(
            row["transitive_definitive"] for row in controls
        ),
        "negative_controls": negatives,
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["transitive_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["transitive_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["linked_controls_passed"] == summary["control_total"] == 32
        and all(negatives.values())
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-transitive-chain/1",
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
