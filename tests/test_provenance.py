from pathlib import Path

import pytest

from agnxiv.provenance import fingerprint_artifact, fingerprint_tree


def test_tree_digest_changes_with_research_content(tmp_path: Path) -> None:
    file = tmp_path / "analysis.py"
    file.write_text("value = 1\n", encoding="utf-8")
    before = fingerprint_tree(tmp_path)

    file.write_text("value = 2\n", encoding="utf-8")
    after = fingerprint_tree(tmp_path)

    assert before.tree_digest != after.tree_digest
    assert before.file_count == 1
    assert after.file_count == 1


def test_file_artifact_fingerprint_changes_with_content(tmp_path: Path) -> None:
    artifact = tmp_path / "checkpoint.bin"
    artifact.write_bytes(b"version-one")
    before = fingerprint_artifact(artifact)

    artifact.write_bytes(b"version-two")
    after = fingerprint_artifact(artifact)

    assert before.kind == "file"
    assert before.sha256 != after.sha256
    assert before.file_count == 1


def test_directory_artifact_is_content_addressed(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "dataset"
    artifact_dir.mkdir()
    (artifact_dir / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    fingerprint = fingerprint_artifact(artifact_dir)

    assert fingerprint.kind == "directory"
    assert fingerprint.file_count == 1
    assert fingerprint.size_bytes > 0


def test_repository_symlink_is_hashed_as_link_not_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / "agnxiv-outside-secret.txt"
    outside.write_text("secret-v1\n", encoding="utf-8")
    link = tmp_path / "linked-secret.txt"

    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    before = fingerprint_tree(tmp_path)
    outside.write_text("secret-v2\n", encoding="utf-8")
    after = fingerprint_tree(tmp_path)

    assert before.tree_digest == after.tree_digest
    assert before.file_count == 1
    assert before.files[0].kind == "symlink"
    assert before.files[0].link_target == str(outside)


def test_explicit_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    target.write_bytes(b"data")
    link = tmp_path / "data-link.bin"

    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError, match="symlinks are not allowed"):
        fingerprint_artifact(link)


def test_tree_fingerprint_fails_closed_if_file_hashing_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "analysis.py"
    target.write_text("value = 1\n", encoding="utf-8")

    def fail(path):
        raise OSError("simulated unreadable evidence")

    monkeypatch.setattr("agnxiv.provenance.sha256_file", fail)

    with pytest.raises(ValueError, match="could not fingerprint repository file"):
        fingerprint_tree(tmp_path)
