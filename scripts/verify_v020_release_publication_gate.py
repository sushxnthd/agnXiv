#!/usr/bin/env python3
"""Fail-closed authorization and asset gate for the v0.2.0 GitHub release."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import tempfile
from pathlib import Path

EXPECTED_RELEASE_ASSETS = {
    "agnxiv-0.2.0-py3-none-any.whl",
    "agnxiv-0.2.0.tar.gz",
    "agnxiv-v0.2.0-external-audit.json",
    "agnxiv-v0.2.0-release-manifest.json",
}
EXPECTED_MANIFEST_ARTIFACTS = EXPECTED_RELEASE_ASSETS - {
    "agnxiv-v0.2.0-release-manifest.json"
}
CONFIRMATION = "PUBLISH v0.2.0"


class GateError(ValueError):
    """A release state failed a publication invariant."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise GateError(reason)


def authorize_preflight(
    *,
    confirmation: str,
    candidate_commit: str,
    branch_head: str,
    release_state: str,
    target_commit: str | None,
) -> dict:
    require(confirmation == CONFIRMATION, "confirmation phrase mismatch")
    require(
        re.fullmatch(r"[0-9a-f]{40}", candidate_commit) is not None,
        "candidate is not a lowercase 40-character commit",
    )
    require(candidate_commit == branch_head, "candidate is not the current branch head")
    require(
        release_state in {"absent", "draft", "tag_only"},
        "release is already public or has an unknown state",
    )
    if release_state == "absent":
        require(target_commit is None, "absent release unexpectedly has a target")
    else:
        require(target_commit == candidate_commit, "existing tag targets another commit")
    return {
        "authorized": True,
        "candidate_commit": candidate_commit,
        "release_state": release_state,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authorize_assets(
    *,
    candidate_commit: str,
    tag: str,
    asset_metadata_path: Path,
    download_dir: Path,
) -> dict:
    metadata = json.loads(asset_metadata_path.read_text(encoding="utf-8"))
    require(isinstance(metadata, list), "asset metadata is not a list")
    names = [asset.get("name") for asset in metadata]
    require(len(names) == len(set(names)), "duplicate release asset name")
    require(set(names) == EXPECTED_RELEASE_ASSETS, "release asset set mismatch")
    require(
        all(asset.get("state") == "uploaded" for asset in metadata),
        "release asset upload is not complete",
    )

    downloaded = {path.name for path in download_dir.iterdir() if path.is_file()}
    require(downloaded == EXPECTED_RELEASE_ASSETS, "downloaded asset set mismatch")
    metadata_by_name = {asset["name"]: asset for asset in metadata}
    for name in EXPECTED_RELEASE_ASSETS:
        require(
            metadata_by_name[name].get("size") == (download_dir / name).stat().st_size,
            f"GitHub metadata size mismatch for {name}",
        )

    manifest_path = download_dir / "agnxiv-v0.2.0-release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "agnxiv.release/1", "manifest schema mismatch")
    require(manifest.get("version") == "0.2.0", "manifest version mismatch")
    require(manifest.get("tag") == tag, "manifest tag mismatch")
    require(manifest.get("commit") == candidate_commit, "manifest commit mismatch")
    require(
        manifest.get("publication_state") == "draft-until-asset-reverification",
        "manifest publication state mismatch",
    )
    acceptance = manifest.get("acceptance", {})
    require(acceptance.get("final_verdict") == "UNABLE_TO_VERIFY", "unsafe verdict")
    require(acceptance.get("false_pass") is False, "false-pass flag is not false")

    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list), "manifest artifacts are not a list")
    artifact_names = [item.get("name") for item in artifacts]
    require(len(artifact_names) == len(set(artifact_names)), "duplicate manifest artifact")
    require(
        set(artifact_names) == EXPECTED_MANIFEST_ARTIFACTS,
        "manifest artifact set mismatch",
    )
    for item in artifacts:
        path = download_dir / item["name"]
        require(path.stat().st_size == item.get("size"), f"manifest size mismatch: {path.name}")
        require(sha256(path) == item.get("sha256"), f"manifest hash mismatch: {path.name}")

    return {
        "authorized": True,
        "candidate_commit": candidate_commit,
        "tag": tag,
        "release_assets": sorted(EXPECTED_RELEASE_ASSETS),
        "verified_payloads": sorted(EXPECTED_MANIFEST_ARTIFACTS),
    }


def valid_fixture(root: Path, candidate: str, tag: str) -> tuple[Path, Path, Path]:
    asset_dir = root / "assets"
    asset_dir.mkdir()
    payloads = {
        "agnxiv-0.2.0-py3-none-any.whl": b"wheel-payload\n",
        "agnxiv-0.2.0.tar.gz": b"sdist-payload\n",
        "agnxiv-v0.2.0-external-audit.json": b'{"verdict":"UNABLE_TO_VERIFY"}\n',
    }
    for name, payload in payloads.items():
        (asset_dir / name).write_bytes(payload)
    manifest = {
        "schema": "agnxiv.release/1",
        "version": "0.2.0",
        "tag": tag,
        "commit": candidate,
        "publication_state": "draft-until-asset-reverification",
        "artifacts": [
            {
                "name": name,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in payloads.items()
        ],
        "acceptance": {"final_verdict": "UNABLE_TO_VERIFY", "false_pass": False},
    }
    manifest_path = asset_dir / "agnxiv-v0.2.0-release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    metadata = [
        {"name": name, "state": "uploaded", "size": (asset_dir / name).stat().st_size}
        for name in sorted(EXPECTED_RELEASE_ASSETS)
    ]
    metadata_path = root / "asset-metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return metadata_path, manifest_path, asset_dir


def run_preflight_matrix() -> dict:
    candidate = "a" * 40
    accepted = false_passes = false_rejects = 0
    total = 0
    for confirm_ok, format_ok, head_ok, state, target_ok in itertools.product(
        (False, True),
        (False, True),
        (False, True),
        ("absent", "draft", "tag_only", "published"),
        (False, True),
    ):
        total += 1
        supplied = candidate if format_ok else "not-a-commit"
        branch_head = supplied if head_ok else "b" * 40
        target = None if state == "absent" and target_ok else (
            supplied if target_ok else "c" * 40
        )
        expected = (
            confirm_ok
            and format_ok
            and head_ok
            and state in {"absent", "draft", "tag_only"}
            and ((state == "absent" and target is None) or (state != "absent" and target == supplied))
        )
        try:
            authorize_preflight(
                confirmation=CONFIRMATION if confirm_ok else "publish",
                candidate_commit=supplied,
                branch_head=branch_head,
                release_state=state,
                target_commit=target,
            )
            observed = True
            accepted += 1
        except GateError:
            observed = False
        false_passes += observed and not expected
        false_rejects += expected and not observed
    return {
        "total_cases": total,
        "accepted_controls": accepted,
        "rejected_cases": total - accepted,
        "false_passes": false_passes,
        "false_rejects": false_rejects,
    }


def run_asset_matrix() -> dict:
    candidate, tag = "a" * 40, "v0.2.0"
    accepted = false_passes = false_rejects = 0
    total = 0
    for bits in itertools.product((False, True), repeat=10):
        total += 1
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata_path, manifest_path, asset_dir = valid_fixture(root, candidate, tag)
            metadata = json.loads(metadata_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            if not bits[0]:
                (asset_dir / "unexpected.bin").write_bytes(b"extra")
                metadata.append({"name": "unexpected.bin", "state": "uploaded", "size": 5})
            if not bits[1]:
                metadata[0]["state"] = "new"
            if not bits[2]:
                metadata[0]["size"] += 1
            if not bits[3]:
                manifest["schema"] = "agnxiv.release/0"
            if not bits[4]:
                manifest["tag"] = "v0.2.0-stale"
            if not bits[5]:
                manifest["commit"] = "b" * 40
            if not bits[6]:
                manifest["publication_state"] = "public"
            if not bits[7]:
                manifest["artifacts"] = manifest["artifacts"][:-1]
            if not bits[8]:
                target = asset_dir / "agnxiv-v0.2.0-external-audit.json"
                target.write_bytes(target.read_bytes() + b"x")
                for item in metadata:
                    if item["name"] == target.name:
                        item["size"] = target.stat().st_size
            if not bits[9]:
                manifest["artifacts"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            for item in metadata:
                if item["name"] == manifest_path.name:
                    item["size"] = manifest_path.stat().st_size
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            expected = all(bits)
            try:
                authorize_assets(
                    candidate_commit=candidate,
                    tag=tag,
                    asset_metadata_path=metadata_path,
                    download_dir=asset_dir,
                )
                observed = True
                accepted += 1
            except GateError:
                observed = False
            false_passes += observed and not expected
            false_rejects += expected and not observed
    return {
        "total_cases": total,
        "accepted_controls": accepted,
        "rejected_cases": total - accepted,
        "false_passes": false_passes,
        "false_rejects": false_rejects,
    }


def run_matrix(output: Path) -> dict:
    report = {
        "schema": "agnxiv.release-publication-gate/1",
        "preflight": run_preflight_matrix(),
        "postdraft_assets": run_asset_matrix(),
    }
    report["overall_passed"] = all(
        section["false_passes"] == 0 and section["false_rejects"] == 0
        for section in (report["preflight"], report["postdraft_assets"])
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--confirmation", required=True)
    preflight.add_argument("--candidate", required=True)
    preflight.add_argument("--branch-head", required=True)
    preflight.add_argument("--release-state", required=True)
    preflight.add_argument("--target-commit")
    assets = sub.add_parser("assets")
    assets.add_argument("--candidate", required=True)
    assets.add_argument("--tag", required=True)
    assets.add_argument("--asset-metadata", type=Path, required=True)
    assets.add_argument("--download-dir", type=Path, required=True)
    matrix = sub.add_parser("matrix")
    matrix.add_argument(
        "--output",
        type=Path,
        default=Path("results/v020_release_publication_gate/results.json"),
    )
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "preflight":
            report = authorize_preflight(
                confirmation=args.confirmation,
                candidate_commit=args.candidate,
                branch_head=args.branch_head,
                release_state=args.release_state,
                target_commit=args.target_commit,
            )
        elif args.command == "assets":
            report = authorize_assets(
                candidate_commit=args.candidate,
                tag=args.tag,
                asset_metadata_path=args.asset_metadata,
                download_dir=args.download_dir,
            )
        else:
            report = run_matrix(args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    except GateError as error:
        print(json.dumps({"authorized": False, "reason": str(error)}, sort_keys=True))
        raise SystemExit(1) from error
    if report.get("overall_passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
