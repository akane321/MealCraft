"""Offline benchmark for requests that change which meals or dishes a week contains."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.agent.shape_change import setup_shape
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShape


def _base_shape(name: str) -> MealPlanShape:
    meals = {"dinner": MEAL_PRESETS["dinner"]["main and vegetable"]}
    if name == "breakfast-dinner":
        meals["breakfast"] = MEAL_PRESETS["breakfast"]["one dish"]
    elif name != "dinner":
        raise ValueError(f"unknown base shape: {name}")
    return MealPlanShape.model_validate({"meals": meals})


def _actual_shape(message: str, base: str, language: str) -> dict[str, list[str] | None] | None:
    result = setup_shape(message, _base_shape(base), "zh" if language == "zh" else "en")
    if result is None:
        return None
    shape, _summary = result
    return {
        meal: [role.role_id for role in shape.meals[meal]] if meal in shape.meals else None
        for meal in ("breakfast", "dinner", "lunch")
    }


def evaluate_meal_shape_changes(*, dataset_path: Path) -> dict[str, Any]:
    cases = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    results = []
    for case in cases:
        actual = _actual_shape(case["message"], case["base"], case["language"])
        results.append(
            {
                **case,
                "actual": actual,
                "exact_match": actual == case["expected"],
            }
        )

    def rates(key: str) -> dict[str, dict[str, float | int]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for result in results:
            groups[result[key]].append(result)
        return {
            label: {
                "case_count": len(group),
                "exact_match_rate": round(sum(row["exact_match"] for row in group) / len(group), 4),
            }
            for label, group in sorted(groups.items())
        }

    return {
        "schema_version": "1.0",
        "evaluation_role": "developer_set",
        "provider": "deterministic-shape-rules",
        "live_api_used": False,
        "dataset": {
            "path": dataset_path.as_posix(),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        },
        "metrics": {
            "case_count": len(results),
            "exact_match_rate": round(sum(row["exact_match"] for row in results) / max(len(results), 1), 4),
            "false_positive_count": sum(row["actual"] is not None and row["expected"] is None for row in results),
            "false_negative_count": sum(row["actual"] is None and row["expected"] is not None for row in results),
        },
        "category_metrics": rates("category"),
        "language_metrics": rates("language"),
        "failure_cases": [row for row in results if not row["exact_match"]],
        "cases": results,
    }
