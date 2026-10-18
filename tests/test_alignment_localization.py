from pathlib import Path

from agnxiv.alignment import (
    LocalizationGold,
    localize_paper_code,
    ranked_paths,
    score_localization,
)


def test_localizer_ranks_matching_procedure_file(tmp_path: Path) -> None:
    (tmp_path / "noise.py").write_text(
        "def helper(value):\n    return value + 1\n",
        encoding="utf-8",
    )
    (tmp_path / "train.py").write_text(
        "loss = cross_entropy(logits, target)\n",
        encoding="utf-8",
    )
    candidates = localize_paper_code(
        "Training minimizes cross entropy loss on the masked prediction target.",
        tmp_path,
    )

    assert ranked_paths(candidates)[0] == "train.py"
    result = score_localization(
        "case",
        candidates,
        LocalizationGold(case_id="case", target_path="train.py"),
    )
    assert result.recall_at_5 is True


def test_localizer_does_not_require_gold_query(tmp_path: Path) -> None:
    (tmp_path / "model.py").write_text(
        "residual = residual - time_var_backcast\n",
        encoding="utf-8",
    )
    candidates = localize_paper_code(
        "Each block updates the residual using the time varying backcast.",
        tmp_path,
    )

    assert candidates
    assert "residual" in candidates[0].shared_tokens
