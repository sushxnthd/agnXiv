"""Exact adversarial matrix for workflow-scoped manifest selection."""

import json
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory

from agnxiv.environment import infer_python_environment


MANIFESTS = (
    "requirements.txt",
    "requirement.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "setup.py",
    "setup.cfg",
)


def content(name: str) -> str:
    if name in {"requirements.txt", "requirement.txt"}:
        return "numpy==1.26.4\n"
    if name.startswith("environment"):
        return "name: frozen\ndependencies:\n  - python=3.8\n  - numpy=1.19\n"
    if name == "pyproject.toml":
        return "[project]\nname='fixture'\nversion='0.0.1'\n"
    if name == "setup.py":
        return "from setuptools import setup\nsetup()\n"
    return "# independent environment metadata\n"


def infer(names, *, root_requirement=None):
    with TemporaryDirectory() as raw:
        root = Path(raw)
        if root_requirement is not None:
            (root / "requirements.txt").write_text(root_requirement, encoding="utf-8")
        scoped = root / "experiment"
        scoped.mkdir()
        (scoped / "evaluate.py").write_text("print('score: 1.0')\n", encoding="utf-8")
        for name in names:
            (scoped / name).write_text(content(name), encoding="utf-8")
        return infer_python_environment(root, scope_paths=["experiment/evaluate.py"])


def main():
    conflicts = []
    for left, right in combinations(MANIFESTS, 2):
        spec = infer((left, right))
        conflicts.append({
            "manifests": [left, right],
            "resolution": spec.scope_resolution,
            "preferred": spec.preferred_dependency_file,
            "install_commands": spec.install_commands,
            "passed": (
                spec.scope_resolution == "ambiguous"
                and spec.preferred_dependency_file is None
                and not spec.install_commands
                and len(spec.dependency_files) == 2
            ),
        })

    controls = []
    for name in MANIFESTS:
        spec = infer((name,))
        controls.append({
            "manifest": name,
            "resolution": spec.scope_resolution,
            "preferred": spec.preferred_dependency_file,
            "passed": spec.scope_resolution == "resolved"
                and spec.preferred_dependency_file == f"experiment/{name}",
        })

    scoped = infer(("requirements.txt",), root_requirement="numpy==2.1.0\n")
    root_precedence = {
        "resolution": scoped.scope_resolution,
        "preferred": scoped.preferred_dependency_file,
        "dependency_files": scoped.dependency_files,
        "passed": scoped.dependency_files == ["experiment/requirements.txt"]
            and scoped.preferred_dependency_file == "experiment/requirements.txt",
    }
    result = {
        "schema": "agnxiv.scoped-environment-conflict/1",
        "pre_fix_counterexample": {
            "manifests": ["requirements.txt", "environment.yml"],
            "observed_resolution": "resolved",
            "observed_preferred": "experiment/requirements.txt",
            "environment_yml_omitted": True,
            "false_accept": True,
        },
        "conflict_cases": len(conflicts),
        "conflict_false_accepts": sum(not item["passed"] for item in conflicts),
        "control_cases": len(controls) + 1,
        "control_failures": sum(not item["passed"] for item in controls)
            + int(not root_precedence["passed"]),
        "conflicts": conflicts,
        "controls": controls,
        "root_scope_precedence": root_precedence,
    }
    output = Path("research/results/scoped-environment-conflicts.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "conflict_cases", "conflict_false_accepts", "control_cases", "control_failures"
    )}, indent=2, sort_keys=True))
    if result["conflict_false_accepts"] or result["control_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

