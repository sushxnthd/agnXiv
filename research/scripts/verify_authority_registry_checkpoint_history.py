#!/usr/bin/env python3
"""Execute the frozen persisted checkpoint-history consistency matrix."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from verify_authority_registry_checkpoint_quorum import CHECKPOINT_KEYS, NOW, POLICY, build, bundle
from verify_authority_registry_checkpoint_snapshot import (
    FAMILIES,
    attest,
    checkpoints,
    registry_pair,
)

from agnxiv.authority import authority_registry_sha256
from agnxiv.models import Verdict
from agnxiv.verdict_gate import gate_hosted_verdict

OUT = Path("research/results/authority-registry-checkpoint-history.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-history-summary.json")


def gate(item, registry, current, observed=None, *, require_history=False):
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
        require_registry_checkpoint_history=require_history,
    )


def run_case(case, family, mode):
    legitimate, fork = registry_pair(family)
    if mode == "attack":
        supplied, current, observed = fork, checkpoints(fork), checkpoints(legitimate)
    elif mode == "matching_control":
        supplied, current, observed = legitimate, checkpoints(legitimate), checkpoints(legitimate)
    elif mode == "prior_epoch_control":
        supplied, current = legitimate, checkpoints(legitimate)
        prior = legitimate.model_copy(deep=True)
        prior.registry_epoch -= 1
        observed = checkpoints(prior)
    else:
        raise ValueError(mode)
    item = bundle(case)
    attest(item, supplied)
    parent = gate(item.model_copy(deep=True), supplied, current)
    corrected = gate(item.model_copy(deep=True), supplied, current, observed, require_history=True)
    reversed_result = gate(
        item.model_copy(deep=True),
        supplied,
        list(reversed(current)),
        list(reversed(observed)),
        require_history=True,
    )
    return {
        "case": case,
        "family": family,
        "mode": mode,
        "supplied_registry": supplied.model_dump(mode="json"),
        "supplied_registry_sha256": authority_registry_sha256(supplied),
        "current_checkpoints": [r.model_dump(mode="json") for r in current],
        "observed_checkpoints": [r.model_dump(mode="json") for r in observed],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "history_bound_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "reversed_order_definitive": reversed_result.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "history_reasons": corrected.verdict_gate_reasons,
    }


def main():
    attacks = [
        run_case(120000 + 100 * i + o, f, "attack")
        for i, f in enumerate(FAMILIES)
        for o in range(32)
    ]
    matching = [run_case(130000 + o, f, "matching_control") for o, f in enumerate(FAMILIES * 8)]
    prior = [run_case(140000 + o, f, "prior_epoch_control") for o, f in enumerate(FAMILIES * 8)]
    legitimate, _ = registry_pair(FAMILIES[0])
    item = bundle(150000)
    attest(item, legitimate)
    current = checkpoints(legitimate)
    missing = gate(item.model_copy(deep=True), legitimate, current, [], require_history=True)
    historical_only = gate(
        item.model_copy(deep=True), legitimate, [], current, require_history=True
    )
    tampered = [r.model_copy(deep=True) for r in current]
    tampered[0].signature_b64 = "AAAA"
    invalid = gate(item.model_copy(deep=True), legitimate, current, tampered, require_history=True)
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(r["parent_definitive"] for r in attacks),
        "history_bound_false_passes": sum(r["history_bound_definitive"] for r in attacks),
        "reversed_order_false_passes": sum(r["reversed_order_definitive"] for r in attacks),
        "matching_control_total": len(matching),
        "matching_controls_passed": sum(r["history_bound_definitive"] for r in matching),
        "prior_epoch_control_total": len(prior),
        "prior_epoch_controls_passed": sum(r["history_bound_definitive"] for r in prior),
        "missing_history_blocked": missing.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "historical_only_quorum_blocked": historical_only.record.verdict
        == Verdict.UNABLE_TO_VERIFY,
        "invalid_history_blocked": invalid.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "families_blocked": {
            f: sum(r["family"] == f and not r["history_bound_definitive"] for r in attacks)
            for f in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == summary["attack_total"] == 128
        and summary["history_bound_false_passes"] == 0
        and summary["reversed_order_false_passes"] == 0
        and summary["matching_controls_passed"] == summary["matching_control_total"] == 32
        and summary["prior_epoch_controls_passed"] == summary["prior_epoch_control_total"] == 32
        and summary["missing_history_blocked"]
        and summary["historical_only_quorum_blocked"]
        and summary["invalid_history_blocked"]
        and all(v == 32 for v in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-history/1",
        "validation_time": NOW.isoformat(),
        "quorum_policy": POLICY.model_dump(mode="json"),
        "checkpoint_keys": [k.model_dump(mode="json") for k in CHECKPOINT_KEYS],
        "attacks": attacks,
        "matching_controls": matching,
        "prior_epoch_controls": prior,
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
