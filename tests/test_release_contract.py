from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agnxiv import __version__


def test_release_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_release_contract.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_version_matches_project_metadata() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert __version__ == metadata["project"]["version"]
