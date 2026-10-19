from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ACTION_SHA = re.compile(r"^[0-9a-f]{40}$")


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def package_version() -> str:
    text = (ROOT / "src/agnxiv/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise ValueError("src/agnxiv/__init__.py is missing __version__")
    return match.group(1)


def workflow_failures() -> list[str]:
    failures: list[str] = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not re.match(r"^(?:-\s*)?uses:\s+", stripped):
                continue
            target = stripped.split("uses:", 1)[1].split("#", 1)[0].strip()
            if target.startswith("./"):
                continue
            if "@" not in target:
                failures.append(f"{path.relative_to(ROOT)}:{index + 1}: unversioned action")
                continue
            ref = target.rsplit("@", 1)[1]
            if not ACTION_SHA.fullmatch(ref):
                failures.append(
                    f"{path.relative_to(ROOT)}:{index + 1}: action is not pinned to a commit SHA"
                )
            if target.startswith("actions/checkout@"):
                nearby = "\n".join(lines[index + 1 : index + 7])
                if "persist-credentials: false" not in nearby:
                    failures.append(
                        f"{path.relative_to(ROOT)}:{index + 1}: checkout persists credentials"
                    )
    return failures


def release_contract_failures() -> list[str]:
    failures: list[str] = []
    pyproject_version = project_version()
    init_version = package_version()

    if not SEMVER.fullmatch(pyproject_version):
        failures.append(f"project version is not stable SemVer: {pyproject_version}")
    if init_version != pyproject_version:
        failures.append(
            f"version mismatch: pyproject={pyproject_version}, package={init_version}"
        )

    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        failures.append("CHANGELOG.md is missing")
    else:
        text = changelog.read_text(encoding="utf-8")
        if f"## [{pyproject_version}]" not in text:
            failures.append(f"CHANGELOG.md has no section for {pyproject_version}")

    notes = ROOT / "docs/releases" / f"v{pyproject_version}.md"
    if not notes.is_file():
        failures.append(f"release notes are missing: {notes.relative_to(ROOT)}")

    dockerfile = ROOT / "Dockerfile.service"
    if not dockerfile.is_file() or "@sha256:" not in dockerfile.read_text(
        encoding="utf-8"
    ).splitlines()[0]:
        failures.append("Dockerfile.service base image is not digest-pinned")

    failures.extend(workflow_failures())
    return failures


def main() -> int:
    failures = release_contract_failures()
    if failures:
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    version = project_version()
    print(f"release contract valid for v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
