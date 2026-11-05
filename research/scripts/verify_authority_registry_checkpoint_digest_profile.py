#!/usr/bin/env python3
"""Execute the frozen artifact digest-semantics substitution matrix."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from verify_authority_registry_checkpoint_artifact_scope import (
    CONSUMER,
    EXECUTION,
    artifact_scope,
    envelopes,
)
from verify_authority_registry_checkpoint_history_commitment import (
    FAMILIES,
    attest,
    bundle,
    chain,
    gate,
)

from agnxiv.authority import (
    RegistryCheckpointArtifactDigestProfile,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
)
from agnxiv.models import Verdict

OUT = Path("research/results/authority-registry-checkpoint-digest-profile.json.gz")
SUMMARY = Path("research/results/authority-registry-checkpoint-digest-profile-summary.json")
TRUSTED = RegistryCheckpointArtifactDigestProfile(
    manuscript="raw-bytes-v1",
    repository_tree="git-tree-v1",
    claim_manifest="jcs-json-v1",
    evidence_bundle="merkle-manifest-v1",
)
ATTACKS = (
    ("manuscript_semantics", "manuscript", "normalized-text-v1"),
    ("repository_tree_semantics", "repository_tree", "archive-bytes-v1"),
    ("claim_manifest_semantics", "claim_manifest", "raw-json-v1"),
    ("evidence_bundle_semantics", "evidence_bundle", "archive-bytes-v1"),
)


def run_case(case, family_index, *, control=False):
    name, field, replacement = ATTACKS[family_index]
    rows = chain(FAMILIES[family_index], recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    effective = TRUSTED if control else TRUSTED.model_copy(update={field: replacement})
    profile_commitment = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact, TRUSTED
    )
    parent = gate(
        item.model_copy(deep=True), rows,
        commitment=rows["commitment"], require_commitment=True,
        consumer_scope=CONSUMER, scoped_commitment=consumer, require_consumer_scope=True,
        execution_scope=EXECUTION, execution_scoped_commitment=execution, require_execution_scope=True,
        artifact_scope=scope, artifact_scoped_commitment=artifact, require_artifact_scope=True,
    )
    corrected = gate(
        item.model_copy(deep=True), rows,
        commitment=rows["commitment"], require_commitment=True,
        consumer_scope=CONSUMER, scoped_commitment=consumer, require_consumer_scope=True,
        execution_scope=EXECUTION, execution_scoped_commitment=execution, require_execution_scope=True,
        artifact_scope=scope, artifact_scoped_commitment=artifact, require_artifact_scope=True,
        digest_profile=effective, digest_profile_scoped_commitment=profile_commitment,
        require_digest_profile=True,
    )
    return {
        "case": case,
        "family": name,
        "control": control,
        "artifact_commitment": artifact,
        "source_profile": TRUSTED.model_dump(mode="json"),
        "effective_profile": effective.model_dump(mode="json"),
        "trusted_profile_commitment": profile_commitment,
        "artifact_scoped_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "profile_scoped_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "profile_scope_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(246000)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    profile_commitment = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(artifact, TRUSTED)

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True), rows,
            commitment=rows["commitment"], require_commitment=True,
            consumer_scope=CONSUMER, scoped_commitment=consumer, require_consumer_scope=True,
            execution_scope=EXECUTION, execution_scoped_commitment=execution, require_execution_scope=True,
            artifact_scope=scope, artifact_scoped_commitment=artifact,
            require_artifact_scope=overrides.get("require_artifact", True),
            digest_profile=overrides.get("profile", TRUSTED),
            digest_profile_scoped_commitment=overrides.get("commitment", profile_commitment),
            require_digest_profile=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_profile_blocked": blocked(profile=None),
        "missing_commitment_blocked": blocked(commitment=None),
        "malformed_commitment_blocked": blocked(commitment="abcd"),
        "without_artifact_mode_blocked": blocked(require_artifact=False),
        **{
            f"wrong_{field}_blocked": blocked(profile=TRUSTED.model_copy(update={field: value}))
            for _, field, value in ATTACKS
        },
    }


def main():
    attacks = [run_case(241000 + 100 * family + offset, family) for family in range(4) for offset in range(32)]
    controls = [run_case(245000 + offset, offset % 4, control=True) for offset in range(32)]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "artifact_scoped_false_passes": sum(row["artifact_scoped_definitive"] for row in attacks),
        "profile_scoped_false_passes": sum(row["profile_scoped_definitive"] for row in attacks),
        "control_total": len(controls),
        "profile_scoped_controls_passed": sum(row["profile_scoped_definitive"] for row in controls),
        "families_blocked": {name: sum(row["family"] == name and not row["profile_scoped_definitive"] for row in attacks) for name, _, _ in ATTACKS},
        "negative_controls": negatives,
    }
    summary["passed"] = summary["artifact_scoped_false_passes"] == summary["attack_total"] == 128 and summary["profile_scoped_false_passes"] == 0 and summary["profile_scoped_controls_passed"] == summary["control_total"] == 32 and all(v == 32 for v in summary["families_blocked"].values()) and all(negatives.values())
    report = {"schema": "agnxiv.authority-registry-checkpoint-digest-profile/1", "attacks": attacks, "controls": controls, "summary": summary}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with OUT.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        compressed.write(encoded)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
