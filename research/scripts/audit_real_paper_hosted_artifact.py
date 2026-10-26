"""Independent audit of the frozen hosted real-paper evidence archive.

This checker intentionally imports no agnxiv production module.  It verifies
the GitHub artifact bytes before opening the single JSON member, then checks
the preregistered environment-firewall prediction against the actual external
paper execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

EXPECTED_ARCHIVE_SHA256 = (
    "fce92fdc1ced72366437cad6830c043520870abbc299a54cb00fdb0e6c3f94cb"
)
EXPECTED_MANUSCRIPT_SHA256 = (
    "f60c57f5c39453638b82b8eb1317db6b9e92d440ddf4b06eaab0a6f3a08605a7"
)
EXPECTED_REPOSITORY_COMMIT = "2f83d0fa506e7af2b72ca191b65ce42e07c9e185"
EXPECTED_OBSERVATIONS = {
    "split_half_r": (0.51, 0.504),
    "spearman_brown": (0.68, 0.67),
}
IMMUTABLE_IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["result"]
    return [result["bundle"], *[item["bundle"] for item in result["additional_verifications"]]]


def audit(archive: Path) -> dict[str, Any]:
    archive_sha256 = _sha256(archive)
    assert archive_sha256 == EXPECTED_ARCHIVE_SHA256

    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["zero-manifest-real.json"]
        raw = zipped.read("zero-manifest-real.json")
    payload = json.loads(raw)

    assert payload["status"] == "needs_review"
    result = payload["result"]
    assert result["kind"] == "verification"
    assert result["zero_manifest"] is True
    assert result["manuscript_identity"] == {
        "arxiv_id": "2604.15702v2",
        "sha256": EXPECTED_MANUSCRIPT_SHA256,
        "expected_sha256": EXPECTED_MANUSCRIPT_SHA256,
        "identity_verified": True,
    }
    assert result["build"]["plan"]["dependency_precision"] == "floating"
    assert IMMUTABLE_IMAGE_RE.fullmatch(result["build"]["base_image_id"])
    assert IMMUTABLE_IMAGE_RE.fullmatch(result["build"]["image_id"])

    observations = []
    for bundle in _bundles(payload):
        metric = bundle["claim"]["metric"]
        expected, observed = EXPECTED_OBSERVATIONS[metric]
        record = bundle["record"]
        reasons = bundle["verdict_gate_reasons"]
        execution = bundle["execution"]

        assert record["expected"] == expected
        assert record["observed_mean"] == observed
        assert record["verdict"] == "UNABLE_TO_VERIFY"
        assert bundle["provisional_verdict"] == "CONTRADICTED"
        assert reasons == [
            "historical dependency fidelity is approximate, not constrained",
            "built dependency manifest precision is floating, not hash-pinned",
        ]
        assert bundle["provenance"]["git"]["commit"] == EXPECTED_REPOSITORY_COMMIT
        assert execution["returncode"] == 0
        assert execution["source_unchanged"] is True
        assert execution["artifacts_unchanged"] is True
        assert execution["image_id"] == result["build"]["image_id"]
        assert IMMUTABLE_IMAGE_RE.fullmatch(execution["image_id"])
        observations.append(
            {
                "metric": metric,
                "reported": expected,
                "observed": observed,
                "public_verdict": record["verdict"],
                "provisional_verdict": bundle["provisional_verdict"],
            }
        )

    assert {item["metric"] for item in observations} == set(EXPECTED_OBSERVATIONS)
    canonical = json.dumps(observations, sort_keys=True, separators=(",", ":"))
    return {
        "schema": "agnxiv.real-paper-hosted-artifact-audit/1",
        "workflow_run": 40116884857,
        "workflow_head": "4cea106867a53377ea264b070e79ce11b5ddcd5a",
        "artifact_id": 12569325839,
        "archive_sha256": archive_sha256,
        "manuscript_identity_verified": True,
        "repository_commit": EXPECTED_REPOSITORY_COMMIT,
        "measurements_preserved": len(observations),
        "false_definitive_verdicts": 0,
        "provisional_comparisons_preserved": len(observations),
        "prediction_matched": True,
        "preserved_archive": (
            "research/evidence/hosted-real-paper/run-40116884857.zip"
        ),
        "observations_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "observations": sorted(observations, key=lambda item: item["metric"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
