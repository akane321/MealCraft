"""Calibrate on the declared real-catalog developer pairs only; never read held-out data.

Run from repository root with PYTHONPATH=backend. Output is reproducible developer
fit evidence, not independent accuracy, a product policy, or a human annotation.
"""

import hashlib
import json
from dataclasses import asdict
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from app.planning.near_duplicate_groups import NearDuplicatePolicy, classify
from app.planning.recipe_pair_similarity import RecipePairIndex

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/fixtures/planning-v2/near-duplicate-dev-v1.json"
OUT = ROOT / "docs/evaluation/algorithm-dev/near-duplicates.json"


def catalog_recipes(keys):
    recipes = {}
    release = ROOT / "data-engineering/data/release/v2.2/recipes.jsonl"
    for line in release.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        key = row["recipe_id"]
        if key in keys:
            recipes[key] = SimpleNamespace(
                external_id=key,
                slug=key,
                title=row["title"],
                recipe_ingredients=[
                    SimpleNamespace(ingredient=SimpleNamespace(normalized_name=i["canonical_name"]))
                    for i in row["ingredients"]
                ],
            )
    for row in json.loads((ROOT / "data/recipes/recipes.json").read_text(encoding="utf-8")):
        key = f"slug:{row['slug']}"
        if key in keys:
            recipes[key] = SimpleNamespace(
                external_id=None,
                slug=row["slug"],
                title=row["title"],
                recipe_ingredients=[
                    SimpleNamespace(ingredient=SimpleNamespace(normalized_name=i["ingredient"]))
                    for i in row["ingredients"]
                ],
            )
    if set(recipes) != set(keys):
        raise ValueError(f"Missing catalog recipes: {set(keys) - set(recipes)}")
    return recipes


def run():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pairs = fixture["pairs"]
    keys = {pair[key] for pair in pairs for key in ("left", "right")}
    recipes = catalog_recipes(keys)
    index = RecipePairIndex(list(recipes.values()))
    signals = [index.compare(pair["left"], pair["right"]) for pair in pairs]
    candidates = []
    for title, ingredients, cosine in product(
        (0.1, 0.2, 0.3, 0.4, 0.5), (0.05, 0.1, 0.2, 0.3, 0.4, 0.5), (0.7, 0.75, 0.8, 0.85, 0.9)
    ):
        policy = NearDuplicatePolicy("real-catalog-dev-v1", title, ingredients, cosine)
        predictions = [classify(signal, policy) for signal in signals]
        fp = sum(pred == "near" and not pair["near"] for pred, pair in zip(predictions, pairs, strict=True))
        fn = sum(pred != "near" and pair["near"] for pred, pair in zip(predictions, pairs, strict=True))
        # False merges first, then missed variants, then the stricter thresholds.
        candidates.append(((fp, fn, -cosine, -ingredients, -title), policy, predictions))
    counts, policy, predictions = min(candidates, key=lambda item: item[0])
    result = {
        "purpose": fixture["purpose"],
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "vector_source": index.vector_source,
        "selection": "min false merges, then misses, then stricter cosine/ingredient/title thresholds",
        "policies_tried": len(candidates),
        "policy": asdict(policy),
        "false_merges": counts[0],
        "missed_variants": counts[1],
        "unknown": predictions.count("unknown"),
        "pairs": [
            {
                **pair,
                "left_title": recipes[pair["left"]].title,
                "right_title": recipes[pair["right"]].title,
                "signals": asdict(signal),
                "prediction": pred,
            }
            for pair, signal, pred in zip(pairs, signals, predictions, strict=True)
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("pairs", "purpose")}, indent=2))


if __name__ == "__main__":
    run()
