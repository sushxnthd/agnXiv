from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v020_publication_is_manual_draft_first_and_asset_verified():
    workflow = (ROOT / ".github/workflows/publish-v0.2.0.yml").read_text(
        encoding="utf-8"
    )
    notes = (ROOT / "docs/RELEASE_NOTES_0_2_0.md").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "environment: agnxiv-release" in workflow
    assert 'assert os.environ["CONFIRM"] == "PUBLISH v0.2.0"' in workflow
    assert "git/ref/heads/${RELEASE_BRANCH}" in workflow
    assert 'test "$current" = "$CANDIDATE_COMMIT"' in workflow
    assert "gh release create" in workflow
    assert "--draft" in workflow
    assert "gh release upload" in workflow
    assert "--clobber" in workflow
    assert '"repos/${GITHUB_REPOSITORY}/releases/${release_id}/assets"' in workflow
    assert '"repos/${GITHUB_REPOSITORY}/releases/assets/${asset_id}"' in workflow
    assert "assert actual == expected" in workflow
    assert 'assert manifest["commit"] == os.environ["CANDIDATE_COMMIT"]' in workflow
    assert '"schema": "agnxiv.release/1"' in workflow
    assert '"publication_state": "draft-until-asset-reverification"' in workflow
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in workflow

    assert "releases/download/v0.2.0/agnxiv-0.2.0-py3-none-any.whl" in notes
    assert "agnxiv doctor" in notes
    assert "agnxiv verify-external" in notes
    assert "UNABLE_TO_VERIFY" in notes
    assert "does not claim PyPI publication" in " ".join(notes.split())
