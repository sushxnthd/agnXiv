from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from agnxiv.build import EnvironmentBuildError, build_python_environment, plan_python_environment
from agnxiv.environment import infer_python_environment

SCICOQA_COMMIT = "463162906459be508ed4a2294fcaede9fa072036"
_MIN_CLASSIFICATION_CASES = 20
_MIN_CLASSIFICATION_ACCURACY = 0.95
_MIN_BUILD_ATTEMPTS = 8
_MIN_BUILD_SUCCESS_RATE = 0.75

_VERSIONED_GITHUB_RE = re.compile(
    r"^https://github\.com/(?P<slug>[^/]+/[^/]+)/tree/(?P<commit>[0-9a-fA-F]{40})/?$"
)


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_exclusions(path: Path | None) -> set[str]:
    if path is None:
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _load_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            versioned = str(row.get("code_url_versioned") or "").strip()
            match = _VERSIONED_GITHUB_RE.match(versioned)
            if not match:
                continue
            key = f"{match.group('slug')}@{match.group('commit').lower()}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "key": key,
                    "slug": match.group("slug"),
                    "commit": match.group("commit").lower(),
                    "paper": row.get("paper_url_versioned") or row.get("paper_url"),
                    "origin_type": row.get("origin_type"),
                }
            )
    return rows


def _clone(slug: str, commit: str, destination: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", str(destination)],
        check=True,
        timeout=30,
    )
    subprocess.run(
        ["git", "-C", str(destination), "remote", "add", "origin", f"https://github.com/{slug}.git"],
        check=True,
        timeout=30,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            commit,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "-q", "--detach", "FETCH_HEAD"],
        check=True,
        timeout=30,
    )


def _ground_truth_source(root: Path) -> str | None:
    if (root / "uv.lock").is_file() or (root / "poetry.lock").is_file():
        return "lockfile"
    if any(
        (root / name).is_file()
        for name in (
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "environment.yml",
            "environment.yaml",
        )
    ):
        return "manifest"
    if any(path.is_file() for path in root.rglob("*.py")):
        return "import_scan"
    return None


def _small_safe_requirements(root: Path) -> bool:
    path = root / "requirements.txt"
    if not path.is_file() or path.is_symlink():
        return False
    active = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not active or len(active) > 20:
        return False
    try:
        plan = plan_python_environment(root, base_image="python:3.11-slim")
    except (OSError, UnicodeError, ValueError):
        return False
    return plan.safe_manifest_only


def _attempt_build(root: Path) -> tuple[bool, str | None, str | None]:
    errors: list[str] = []
    for image in (
        "python:3.7-slim",
        "python:3.9-slim",
        "python:3.8-slim",
        "python:3.10-slim",
        "python:3.11-slim",
        "python:3.12-slim",
    ):
        try:
            result = build_python_environment(
                root,
                base_image=image,
                timeout_seconds=180,
            )
        except EnvironmentBuildError as exc:
            errors.append(f"{image}: {str(exc)[-500:]}")
            continue
        return True, image, result.plan.dependency_precision
    return False, None, " | ".join(errors)[-1500:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--exclude")
    parser.add_argument("--max-classification", type=int, default=30)
    parser.add_argument("--max-builds", type=int, default=8)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    exclusions = _load_exclusions(Path(args.exclude) if args.exclude else None)
    candidates = [
        row
        for row in _load_rows([Path(value) for value in args.input])
        if row["key"] not in exclusions
    ]
    candidates.sort(key=lambda row: _stable_key(row["key"] + "|agnxiv-env-heldout-v1"))

    classification_rows: list[dict] = []
    build_rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="agnxiv-env-validation-") as temp:
        base = Path(temp)
        for row in candidates:
            classified_count = sum(
                item.get("status") == "classified"
                for item in classification_rows
            )
            if (
                classified_count >= args.max_classification
                and len(build_rows) >= args.max_builds
            ):
                break

            checkout = base / hashlib.sha256(row["key"].encode()).hexdigest()[:16]
            try:
                _clone(row["slug"], row["commit"], checkout)
            except (subprocess.SubprocessError, OSError) as exc:
                classification_rows.append(
                    {
                        **row,
                        "status": "clone_failed",
                        "matched": False,
                        "error": str(exc),
                    }
                )
                shutil.rmtree(checkout, ignore_errors=True)
                continue

            expected = _ground_truth_source(checkout)
            if expected is None:
                shutil.rmtree(checkout, ignore_errors=True)
                continue

            inferred = infer_python_environment(checkout)
            matched = inferred.dependency_source == expected
            classification_rows.append(
                {
                    **row,
                    "status": "classified",
                    "expected_dependency_source": expected,
                    "inferred_dependency_source": inferred.dependency_source,
                    "dependency_precision": inferred.dependency_precision,
                    "historical_fidelity": inferred.historical_fidelity,
                    "matched": matched,
                }
            )

            if len(build_rows) < args.max_builds and _small_safe_requirements(checkout):
                success, image, detail = _attempt_build(checkout)
                build_rows.append(
                    {
                        **row,
                        "success": success,
                        "base_image": image,
                        "detail": detail,
                    }
                )

            shutil.rmtree(checkout, ignore_errors=True)

            classified_count = sum(
                item.get("status") == "classified"
                for item in classification_rows
            )
            if classified_count >= args.max_classification and len(build_rows) >= args.max_builds:
                break

    classified = [row for row in classification_rows if row.get("status") == "classified"]
    classification_accuracy = (
        sum(bool(row["matched"]) for row in classified) / len(classified)
        if classified
        else 0.0
    )
    build_successes = sum(bool(row["success"]) for row in build_rows)
    build_success_rate = build_successes / len(build_rows) if build_rows else 0.0

    passed = (
        len(classified) >= _MIN_CLASSIFICATION_CASES
        and classification_accuracy >= _MIN_CLASSIFICATION_ACCURACY
        and len(build_rows) >= _MIN_BUILD_ATTEMPTS
        and build_success_rate >= _MIN_BUILD_SUCCESS_RATE
    )

    report = {
        "schema_version": "agnxiv.historical-environment-validation/1",
        "evaluation_role": "heldout_external_historical_environment",
        "source": {
            "dataset": "SciCoQA v1.1",
            "repository": "UKPLab/scicoqa",
            "commit": SCICOQA_COMMIT,
            "sampling_seed": "agnxiv-env-heldout-v1",
        },
        "scope": (
            "Pinned historical research repositories are cloned at their SciCoQA "
            "commit. AgnXiv must recover the dependency-source class correctly, "
            "then successfully construct a dependency-only Docker environment for "
            "a deterministic subset with small safe requirements manifests."
        ),
        "thresholds": {
            "minimum_classification_cases": _MIN_CLASSIFICATION_CASES,
            "minimum_classification_accuracy": _MIN_CLASSIFICATION_ACCURACY,
            "minimum_build_attempts": _MIN_BUILD_ATTEMPTS,
            "minimum_build_success_rate": _MIN_BUILD_SUCCESS_RATE,
        },
        "candidate_repositories": len(candidates),
        "excluded_development_repositories": len(exclusions),
        "classification_cases": len(classified),
        "classification_accuracy": classification_accuracy,
        "build_attempts": len(build_rows),
        "build_successes": build_successes,
        "build_success_rate": build_success_rate,
        "passed": passed,
        "classification_results": classification_rows,
        "build_results": build_rows,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if not passed:
        raise SystemExit(
            "historical environment gate failed: "
            f"classification={len(classified)} @ {classification_accuracy:.3f}, "
            f"builds={build_successes}/{len(build_rows)}"
        )


if __name__ == "__main__":
    main()
