#!/usr/bin/env python3
"""Frozen adversarial verification of dependency-manifest snapshot binding."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agnxiv.build import EnvironmentBuildError, build_python_environment

OUT = Path("research/results/dependency-manifest-snapshot.json")


def manifest(label: str) -> str:
    artifact = hashlib.sha256(label.encode("utf-8")).hexdigest()
    return f"package-{label}==1.0 --hash=sha256:{artifact}\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def attack(index: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agnxiv-manifest-attack-") as temp:
        root = Path(temp)
        path = root / "requirements.txt"
        before = manifest(f"a-{index}")
        after = manifest(f"b-{index}")
        path.write_text(before, encoding="utf-8")
        docker_called = False

        def resolve(image: str) -> str:
            if not image.startswith("agnxiv-env:"):
                path.write_text(after, encoding="utf-8")
                return "sha256:" + "a" * 64
            return "sha256:" + "b" * 64

        def run(*args, **kwargs):
            nonlocal docker_called
            docker_called = True
            return SimpleNamespace(returncode=0, stdout="built", stderr="")

        rejected = False
        with (
            patch("agnxiv.build.resolve_local_image_id", side_effect=resolve),
            patch(
                "agnxiv.build.resolve_local_image_digest_ref",
                return_value="python@sha256:" + "c" * 64,
            ),
            patch("agnxiv.build.subprocess.run", side_effect=run),
        ):
            try:
                build_python_environment(root)
            except EnvironmentBuildError as exc:
                rejected = "changed after build planning" in str(exc)

        old_plan_digest = sha256_text(before)
        old_built_digest = sha256_text(after)
        old_false_accept = old_plan_digest != old_built_digest
        passed = old_false_accept and rejected and not docker_called
        return {
            "case": index,
            "planned_sha256": old_plan_digest,
            "mutated_sha256": old_built_digest,
            "old_false_accept": old_false_accept,
            "rejected_before_docker": rejected and not docker_called,
            "passed": passed,
        }


def control(index: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agnxiv-manifest-control-") as temp:
        root = Path(temp)
        value = manifest(f"control-{index}")
        (root / "requirements.txt").write_text(value, encoding="utf-8")
        copied_digest = ""

        def resolve(image: str) -> str:
            return "sha256:" + ("b" if image.startswith("agnxiv-env:") else "a") * 64

        def run(command, **kwargs):
            nonlocal copied_digest
            copied_digest = sha256_text(
                (Path(command[-1]) / "requirements.txt").read_text(encoding="utf-8")
            )
            iidfile = Path(command[command.index("--iidfile") + 1])
            iidfile.write_text("sha256:" + "b" * 64 + "\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="built", stderr="")

        with (
            patch("agnxiv.build.resolve_local_image_id", side_effect=resolve),
            patch(
                "agnxiv.build.resolve_local_image_digest_ref",
                return_value="python@sha256:" + "c" * 64,
            ),
            patch("agnxiv.build.subprocess.run", side_effect=run),
        ):
            result = build_python_environment(root)
        expected = sha256_text(value)
        passed = result.plan.dependency_sha256 == copied_digest == expected
        return {
            "case": index,
            "planned_sha256": result.plan.dependency_sha256,
            "copied_sha256": copied_digest,
            "passed": passed,
        }


def main() -> None:
    attacks = [attack(index) for index in range(128)]
    controls = [control(index) for index in range(16)]
    transcript = json.dumps(
        {"attacks": attacks, "controls": controls},
        sort_keys=True,
        separators=(",", ":"),
    )
    summary = {
        "attacks": len(attacks),
        "old_false_accepts": sum(bool(row["old_false_accept"]) for row in attacks),
        "rejected_before_docker": sum(
            bool(row["rejected_before_docker"]) for row in attacks
        ),
        "controls": len(controls),
        "controls_passed": sum(bool(row["passed"]) for row in controls),
        "digest": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "passed": all(bool(row["passed"]) for row in attacks + controls),
    }
    result = {
        "schema": "agnxiv.dependency-manifest-snapshot/1",
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
