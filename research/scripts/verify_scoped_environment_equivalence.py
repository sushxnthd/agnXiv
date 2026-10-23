"""Frozen exact-byte evaluation for requirements-alias equivalence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agnxiv.environment import infer_python_environment

POSITIVE_PAYLOADS = {
    "pins": b"numpy==1.26.4\nscipy==1.11.4\n",
    "markers": b'numpy==1.26.4; python_version < "3.12"\n',
    "url_hash": b"wheel @ https://example.invalid/w.whl#sha256=abc\n",
    "include": b"-c constraints.txt\n-r base.txt\n",
    "comments": b"# frozen environment\nnumpy==1.26.4\n",
    "blank": b"",
    "crlf": b"numpy==1.26.4\r\n",
    "non_utf8": b"# provenance: \xff\nnumpy==1.26.4\n",
}

NEGATIVE_PAIRS = {
    "version": (b"numpy==1.26.4\n", b"numpy==2.1.0\n"),
    "marker": (
        b'numpy==1.26.4; python_version < "3.12"\n',
        b'numpy==1.26.4; python_version >= "3.12"\n',
    ),
    "url_hash": (
        b"wheel @ https://example.invalid/w.whl#sha256=abc\n",
        b"wheel @ https://example.invalid/w.whl#sha256=def\n",
    ),
    "option": (b"--pre\nnumpy==1.26.4\n", b"numpy==1.26.4\n"),
    "include": (b"-r base.txt\n", b"-r other.txt\n"),
    "comment": (b"# source A\nnumpy==1.26.4\n", b"# source B\nnumpy==1.26.4\n"),
    "whitespace": (b"numpy==1.26.4\n", b"numpy==1.26.4 \n"),
    "newline": (b"numpy==1.26.4\n", b"numpy==1.26.4\r\n"),
    "order": (
        b"numpy==1.26.4\nscipy==1.11.4\n",
        b"scipy==1.11.4\nnumpy==1.26.4\n",
    ),
    "encoding": (b"# cafe\n", b"# caf\xe9\n"),
    "extra_dependency": (b"numpy==1.26.4\n", b"numpy==1.26.4\nscipy==1.11.4\n"),
    "trailing_blank": (b"numpy==1.26.4\n", b"numpy==1.26.4\n\n"),
}


def evaluate(left: bytes, right: bytes) -> tuple[dict, dict]:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        scoped = root / "experiment"
        scoped.mkdir()
        (scoped / "evaluate.py").write_text("print('score: 1.0')\n", encoding="utf-8")
        requirements = scoped / "requirements.txt"
        alias = scoped / "requirement.txt"
        requirements.write_bytes(left)
        alias.write_bytes(right)
        spec = infer_python_environment(root, scope_paths=["experiment/evaluate.py"])

        # Independent check: recompute from fixture bytes and public output only;
        # do not import or call the production equivalence helper.
        equal = requirements.read_bytes() == alias.read_bytes()
        digest = hashlib.sha256(requirements.read_bytes()).hexdigest() if equal else None
        independent = {
            "equal": equal,
            "expected_digest": digest,
            "reported_digest": spec.manifest_equivalence_sha256,
            "passed": spec.manifest_equivalence_sha256 == digest,
        }
        observed = {
            "resolution": spec.scope_resolution,
            "preferred": spec.preferred_dependency_file,
            "dependency_files": sorted(spec.dependency_files),
            "install_commands": spec.install_commands,
            "digest": spec.manifest_equivalence_sha256,
        }
        return observed, independent


def main() -> None:
    positives = []
    for name, payload in POSITIVE_PAYLOADS.items():
        observed, independent = evaluate(payload, payload)
        passed = (
            observed["resolution"] == "resolved"
            and observed["preferred"] == "experiment/requirements.txt"
            and observed["dependency_files"]
            == ["experiment/requirement.txt", "experiment/requirements.txt"]
            and observed["install_commands"]
            == [["python", "-m", "pip", "install", "-r", "experiment/requirements.txt"]]
            and independent["passed"]
        )
        positives.append({"case": name, "passed": passed, **observed, "independent": independent})

    negatives = []
    for name, (left, right) in NEGATIVE_PAIRS.items():
        observed, independent = evaluate(left, right)
        passed = (
            observed["resolution"] == "ambiguous"
            and observed["preferred"] is None
            and not observed["install_commands"]
            and observed["digest"] is None
            and independent["passed"]
        )
        negatives.append({"case": name, "passed": passed, **observed, "independent": independent})

    result = {
        "schema": "agnxiv.scoped-environment-equivalence/1",
        "certificate": "sha256(exact manifest bytes)",
        "positive_cases": len(positives),
        "positive_failures": sum(not item["passed"] for item in positives),
        "negative_cases": len(negatives),
        "false_accepts": sum(not item["passed"] for item in negatives),
        "independent_checks": len(positives) + len(negatives),
        "independent_failures": sum(
            not item["independent"]["passed"] for item in positives + negatives
        ),
        "positives": positives,
        "negatives": negatives,
        "limits": [
            "Exact bytes only; semantic normalization is deliberately excluded.",
            "Only requirements.txt plus requirement.txt in one directory are eligible.",
            "The certificate does not establish historical environment fidelity.",
        ],
    }
    output = Path("research/results/scoped-environment-equivalence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_keys = (
        "positive_cases",
        "positive_failures",
        "negative_cases",
        "false_accepts",
        "independent_checks",
        "independent_failures",
    )
    print(json.dumps({key: result[key] for key in summary_keys}, indent=2, sort_keys=True))
    if result["positive_failures"] or result["false_accepts"] or result["independent_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
