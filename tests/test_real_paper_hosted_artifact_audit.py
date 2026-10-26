import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

SCRIPT = Path("research/scripts/audit_real_paper_hosted_artifact.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("real_paper_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_rejects_archive_outside_frozen_digest(tmp_path, monkeypatch) -> None:
    module = _load_module()
    payload = {"status": "needs_review"}
    archive = tmp_path / "evidence.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("zero-manifest-real.json", json.dumps(payload))

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(module, "EXPECTED_ARCHIVE_SHA256", digest)
    payload["status"] = "succeeded"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("zero-manifest-real.json", json.dumps(payload))

    try:
        module.audit(archive)
    except AssertionError:
        pass
    else:
        raise AssertionError("mutated archive crossed the frozen digest gate")
