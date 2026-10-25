#!/usr/bin/env python3
"""Adversarial matrix for coherent base digest and image-ID binding."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import agnxiv.build as build_module
from agnxiv.build import EnvironmentBuildError, build_python_environment

OUT = Path("research/results/base-identity-coherence.json")


def image_id(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def digest_ref(label: str) -> str:
    return "python@sha256:" + hashlib.sha256(label.encode()).hexdigest()


def exercise(root: Path, case: int, *, attack: bool) -> dict:
    repository = root / f"case-{case}"
    repository.mkdir()
    mutable = "python:3.11-slim"
    before_id = image_id(f"endpoint-a-{case}")
    bound_id = image_id(f"bound-b-{case}" if attack else f"endpoint-a-{case}")
    immutable = digest_ref(f"bound-b-{case}" if attack else f"endpoint-a-{case}")
    built_id = image_id(f"built-{case}")
    resolved: list[str] = []

    def fake_digest(image: str) -> str:
        assert image == mutable
        return immutable

    def fake_id(image: str) -> str:
        resolved.append(image)
        if image == mutable:
            return before_id
        assert image == immutable
        return bound_id

    def fake_run(command, **kwargs):
        Path(command[command.index("--iidfile") + 1]).write_text(
            built_id + "\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    build_module.resolve_local_image_digest_ref = fake_digest
    build_module.resolve_local_image_id = fake_id
    build_module.subprocess.run = fake_run
    result = build_python_environment(repository, base_image=mutable)
    old_false_accept = attack and before_id != bound_id
    coherent = (
        result.plan.base_image == immutable
        and result.base_image_id == bound_id
        and result.image_id == built_id
        and resolved == [immutable, immutable]
    )
    return {
        "case": case,
        "attack": attack,
        "old_endpoint_id": before_id,
        "bound_digest": immutable,
        "bound_id": bound_id,
        "old_false_accept": old_false_accept,
        "corrected_coherent": coherent,
        "mutable_id_lookups": sum(item == mutable for item in resolved),
    }


def main() -> None:
    original_digest = build_module.resolve_local_image_digest_ref
    original_id = build_module.resolve_local_image_id
    original_run = build_module.subprocess.run
    try:
        with tempfile.TemporaryDirectory(prefix="agnxiv-base-coherence-") as temp:
            root = Path(temp)
            attacks = [exercise(root, case, attack=True) for case in range(128)]
            controls = [
                exercise(root, 1000 + case, attack=False) for case in range(16)
            ]

            malformed = 0
            for case in range(4):
                repository = root / f"malformed-{case}"
                repository.mkdir()
                immutable = digest_ref(f"malformed-{case}")
                build_module.resolve_local_image_digest_ref = lambda image, value=immutable: value
                build_module.resolve_local_image_id = lambda image: "sha256:malformed"
                build_module.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("build must not run")
                )
                try:
                    build_python_environment(repository)
                except EnvironmentBuildError:
                    malformed += 1

            mismatches = 0
            for case in range(16):
                repository = root / f"mismatch-{case}"
                repository.mkdir()
                immutable = digest_ref(f"mismatch-{case}")
                identities = iter(
                    [image_id(f"before-{case}"), image_id(f"after-{case}")]
                )
                build_module.resolve_local_image_digest_ref = lambda image, value=immutable: value
                build_module.resolve_local_image_id = lambda image, values=identities: next(values)

                def fake_run(command, _case=case, **kwargs):
                    Path(command[command.index("--iidfile") + 1]).write_text(
                        image_id(f"built-mismatch-{_case}") + "\n", encoding="utf-8"
                    )
                    return SimpleNamespace(returncode=0, stdout="built", stderr="")

                build_module.subprocess.run = fake_run
                try:
                    build_python_environment(repository)
                except EnvironmentBuildError:
                    mismatches += 1
    finally:
        build_module.resolve_local_image_digest_ref = original_digest
        build_module.resolve_local_image_id = original_id
        build_module.subprocess.run = original_run

    cases = attacks + controls
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":"))
    summary = {
        "attack_total": len(attacks),
        "old_baseline_false_accepts": sum(row["old_false_accept"] for row in attacks),
        "corrected_attack_coherence": sum(row["corrected_coherent"] for row in attacks),
        "mutable_id_lookups": sum(row["mutable_id_lookups"] for row in cases),
        "control_total": len(controls),
        "controls_preserved": sum(row["corrected_coherent"] for row in controls),
        "malformed_total": 4,
        "malformed_rejected": malformed,
        "post_bind_mismatch_total": 16,
        "post_bind_mismatch_rejected": mismatches,
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
    }
    summary["passed"] = (
        summary["old_baseline_false_accepts"] == 128
        and summary["corrected_attack_coherence"] == 128
        and summary["mutable_id_lookups"] == 0
        and summary["controls_preserved"] == 16
        and summary["malformed_rejected"] == 4
        and summary["post_bind_mismatch_rejected"] == 16
    )
    payload = {
        "schema": "agnxiv.base-identity-coherence/1",
        "summary": summary,
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
