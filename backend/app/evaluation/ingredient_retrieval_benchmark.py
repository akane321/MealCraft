"""Offline retrieval metrics for developer-authored ingredient-name matching cases."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases, catalog_vectors
from app.core.paths import repository_root


def _catalog_names() -> dict[str, str]:
    rows = json.loads((repository_root() / "data/ingredients/ingredients.json").read_text(encoding="utf-8"))
    names = {key: key.replace("_", " ") for key in catalog_vectors()}
    names.update({row["normalized_name"]: row["display_name"] for row in rows})
    return names


def evaluate_ingredient_retrieval(*, datasets: dict[str, Path], limit: int = 4) -> dict[str, Any]:
    """Measure a local spelling-and-alias baseline; this function never calls an embedding API."""
    matcher = IngredientMatcher(_catalog_names(), aliases=catalog_aliases(), mode="spelling")
    results = []
    dataset_hashes = {}
    for dataset_name, path in sorted(datasets.items()):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        dataset_hashes[dataset_name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for case in raw["cases"]:
            accepted = set(case["accept"])
            candidates = matcher.suggest(case["term"], limit=limit)
            results.append(
                {
                    "dataset": dataset_name,
                    "term": case["term"],
                    "kind": case.get("kind", "unspecified"),
                    "accepted": sorted(accepted),
                    "candidates": candidates,
                    "top1_hit": bool(accepted & set(candidates[:1])) if accepted else None,
                    "top4_hit": bool(accepted & set(candidates[:limit])) if accepted else None,
                    "empty_accept_returned_candidates": not accepted and bool(candidates),
                }
            )

    def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        positive = [row for row in rows if row["accepted"]]
        return {
            "case_count": len(rows),
            "positive_case_count": len(positive),
            "recall_at_1": round(sum(row["top1_hit"] for row in positive) / max(len(positive), 1), 4),
            "recall_at_4": round(sum(row["top4_hit"] for row in positive) / max(len(positive), 1), 4),
            "none_case_count": len(rows) - len(positive),
            "none_cases_returning_candidates": sum(row["empty_accept_returned_candidates"] for row in rows),
        }

    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_dataset[result["dataset"]].append(result)
        by_kind[result["kind"]].append(result)
    return {
        "schema_version": "1.0",
        "evaluation_role": "developer_set",
        "provider": "local-spelling-and-alias",
        "live_api_used": False,
        "embedding_retrieval_measured": False,
        "limit": limit,
        "dataset_sha256": dataset_hashes,
        "metrics": metrics(results),
        "dataset_metrics": {name: metrics(rows) for name, rows in sorted(by_dataset.items())},
        "kind_metrics": {name: metrics(rows) for name, rows in sorted(by_kind.items())},
        "failure_cases": [row for row in results if row["accepted"] and not row["top4_hit"]],
        "cases": results,
    }
