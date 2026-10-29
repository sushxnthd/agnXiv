#!/usr/bin/env python3
"""Execute the frozen detached checkpoint-history attack matrix."""

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

OUT = Path("research/results/authority-registry-checkpoint-chain.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-chain-summary.json")


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


def gate(item, registry, current, observed, *, chain):
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
        require_registry_checkpoint_chain=chain,
    )


def run_case(case, family, *, control=False):
    legitimate, fork = registry_pair(family)
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    current_registry = (legitimate if control else fork).model_copy(deep=True)
    current_registry.registry_epoch = CURRENT_EPOCH + 1
    observed = checkpoints(prior)
    correct_link = statement_digest(prior)
    link = correct_link if control else hashlib.sha256(
        f"detached:{case}:{family}".encode()
    ).hexdigest()
    current = checkpoints(current_registry, link)
    item = bundle(case)
    attest(item, current_registry)
    parent = gate(item.model_copy(deep=True), current_registry, current, observed, chain=False)
    corrected = gate(item.model_copy(deep=True), current_registry, current, observed, chain=True)
    reversed_result = gate(
        item.model_copy(deep=True),
        current_registry,
        list(reversed(current)),
        list(reversed(observed)),
        chain=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "prior_registry": prior.model_dump(mode="json"),
        "current_registry": current_registry.model_dump(mode="json"),
        "prior_registry_sha256": authority_registry_sha256(prior),
        "current_registry_sha256": authority_registry_sha256(current_registry),
        "expected_previous_statement_sha256": correct_link,
        "supplied_previous_statement_sha256": link,
        "observed_checkpoints": [row.model_dump(mode="json") for row in observed],
        "current_checkpoints": [row.model_dump(mode="json") for row in current],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "chain_bound_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "reversed_order_definitive": reversed_result.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "chain_reasons": corrected.verdict_gate_reasons,
    }


def adversarial_controls():
    legitimate, _ = registry_pair(FAMILIES[0])
    prior = legitimate.model_copy(deep=True)
    prior.registry_epoch = CURRENT_EPOCH
    older = legitimate.model_copy(deep=True)
    older.registry_epoch = CURRENT_EPOCH - 1
    current_registry = legitimate.model_copy(deep=True)
    current_registry.registry_epoch = CURRENT_EPOCH + 1
    item = bundle(170000)
    attest(item, current_registry)
    observed = checkpoints(prior)
    correct = statement_digest(prior)
    missing = gate(item.model_copy(deep=True), current_registry, checkpoints(current_registry), observed, chain=True)
    malformed = gate(item.model_copy(deep=True), current_registry, checkpoints(current_registry, "abcd"), observed, chain=True)
    mixed_rows = [
        checkpoints(current_registry, correct)[0],
        checkpoints(current_registry, "0" * 64)[1],
    ]
    mixed = gate(item.model_copy(deep=True), current_registry, mixed_rows, observed, chain=True)
    same_epoch = prior.model_copy(deep=True)
    same_epoch.registry_epoch = current_registry.registry_epoch
    same = gate(
        item.model_copy(deep=True),
        current_registry,
        checkpoints(current_registry, statement_digest(same_epoch)),
        checkpoints(same_epoch),
        chain=True,
    )
    stale = gate(
        item.model_copy(deep=True),
        current_registry,
        checkpoints(current_registry, statement_digest(older)),
        [*checkpoints(older), *observed],
        chain=True,
    )
    absent = gate(item.model_copy(deep=True), current_registry, checkpoints(current_registry, correct), [], chain=True)
    return {
        "missing_link_blocked": missing.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "malformed_link_blocked": malformed.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "mixed_signer_links_blocked": mixed.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "same_epoch_link_blocked": same.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "stale_nonlatest_link_blocked": stale.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "absent_history_blocked": absent.record.verdict == Verdict.UNABLE_TO_VERIFY,
    }


def main():
    attacks = [
        run_case(160000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(165000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    negative_controls = adversarial_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "chain_bound_false_passes": sum(row["chain_bound_definitive"] for row in attacks),
        "reversed_order_false_passes": sum(row["reversed_order_definitive"] for row in attacks),
        "control_total": len(controls),
        "linked_controls_passed": sum(row["chain_bound_definitive"] for row in controls),
        "negative_controls": negative_controls,
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["chain_bound_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["chain_bound_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["linked_controls_passed"] == summary["control_total"] == 32
        and all(summary["negative_controls"].values())
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-chain/1",
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
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
