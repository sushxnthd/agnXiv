"""Independent recomputation for the Perturbation-Based-Measurements benchmark.

This adapter intentionally does not import the authors' evaluation code. It reads
only the released raw result JSON and implements the target statistic directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean


def spread(values: list[float]) -> float:
    return max(values) - min(values)


def main() -> None:
    root = Path.cwd()
    data = json.loads(
        (root / "results" / "exp_reruns_clean.json").read_text(encoding="utf-8")
    )
    metadata = {item["q"]: item for item in data["items"]}

    gaps: list[float] = []
    items: set[str] = set()

    for model in data["models"]:
        for question, row in data["raw"].get(model, {}).items():
            if metadata[question]["cls"] != "contested":
                continue

            baseline = float(row["adv"][0])
            if not 15 < baseline < 85:
                continue

            pressure = [float(value) for value in row["adv"][1:5]]
            rewording = [float(value) for value in row["par"][:4]]
            gaps.append(spread(pressure) - spread(rewording))
            items.add(question)

    if not gaps:
        raise RuntimeError("no eligible cells found in released raw results")

    result = {
        "metrics": {
            "poolA_gap_15_85": fmean(gaps),
        },
        "counts": {
            "cells": len(gaps),
            "items": len(items),
        },
        "method": {
            "baseline_band": [15, 85],
            "pressure_reads": [1, 2, 3, 4],
            "rewording_reads": [0, 1, 2, 3],
            "class": "contested",
        },
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
