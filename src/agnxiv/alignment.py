from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .research import ResearchCase


class DiscrepancyGold(BaseModel):
    case_id: str
    category: Literal[
        "algorithm_state_update",
        "implementation_scope_initialization",
        "objective_loss_masking",
        "evaluation_protocol_leakage",
    ]
    severity: Literal[
        "clarified_scope",
        "material_unclear",
        "potentially_material",
    ]
    target_summary: str
    author_response_status: Literal["none", "clarified", "community_discussion"]
    origin_url: str
    detector_visible: Literal[False] = False


class DetectorCase(BaseModel):
    case_id: str
    paper_url: str
    repository: str
    commit: str


def detector_view(case: ResearchCase) -> DetectorCase:
    """Return the information allowed to a blind paper-code discrepancy detector."""
    if not case.repository or not case.commit:
        raise ValueError("detector case requires repository and pinned commit")
    paper_url = case.paper_url_versioned or case.paper_url
    return DetectorCase(
        case_id=case.case_id,
        paper_url=paper_url,
        repository=case.repository,
        commit=case.commit,
    )


def load_discrepancy_gold(path: str | Path) -> dict[str, DiscrepancyGold]:
    rows: dict[str, DiscrepancyGold] = {}
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            item = DiscrepancyGold.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"invalid discrepancy gold row on line {line_number}: {exc}"
            ) from exc
        if item.case_id in rows:
            raise ValueError(f"duplicate discrepancy gold case: {item.case_id}")
        rows[item.case_id] = item
    return rows
