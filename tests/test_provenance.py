from pathlib import Path

from agnxiv.provenance import fingerprint_tree


def test_tree_digest_changes_with_research_content(tmp_path: Path) -> None:
    file = tmp_path / "analysis.py"
    file.write_text("value = 1\n", encoding="utf-8")
    before = fingerprint_tree(tmp_path)

    file.write_text("value = 2\n", encoding="utf-8")
    after = fingerprint_tree(tmp_path)

    assert before.tree_digest != after.tree_digest
    assert before.file_count == 1
    assert after.file_count == 1
