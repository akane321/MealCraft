"""Embed every catalog recipe once, for matching a household's words when they ask to swap a meal.

    PYTHONPATH="backend;scripts" python scripts/embed_recipes.py

Needs OPENAI_API_KEY in .env. About 9,000 short texts (~360k tokens, about one US cent). Vectors are
unit-length, quantised to int8 and written as raw bytes (about 2.3 MB), so the runtime needs no numpy and
no vector database. Rerun when the catalog's recipes change.
"""

import hashlib
import json
from pathlib import Path

from embed_ingredients import embedder

RELEASE = Path("data-engineering/data/release/v2.1/recipes.jsonl")
CURATED = Path("data/recipes/recipes.json")
OUT = Path("data/recipes/embeddings-v1")  # .json (keys, model) and .bin (int8 rows)
SCALE = 127


def recipe_texts() -> dict[str, str]:
    """Key -> text. Release recipes by their release id, curated ones as `slug:<slug>`."""
    texts = {}
    for line in RELEASE.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ingredients = list(dict.fromkeys(item["canonical_name"] for item in r["ingredients"]))[:12]
        texts[r["recipe_id"]] = (
            f"{r['title']}. {r['cuisine'].replace('_', ' ')} {r['course'].replace('_', ' ')}. "
            f"Made with {', '.join(ingredients)}."
        )
    for r in json.loads(CURATED.read_text(encoding="utf-8")):
        ingredients = [item["ingredient"].replace("_", " ") for item in r["ingredients"]][:12]
        texts[f"slug:{r['slug']}"] = (
            f"{r['title']}. {r['cuisine']} {r['meal_type']}. Made with {', '.join(ingredients)}."
        )
    return texts


def main() -> None:
    texts = recipe_texts()
    vectors = embedder().embed_documents(list(texts.values()), chunk_size=500)
    rows = bytearray()
    for vector in vectors:
        norm = sum(x * x for x in vector) ** 0.5 or 1.0
        rows += bytes((round(max(-1.0, min(1.0, x / norm)) * SCALE)) & 0xFF for x in vector)
    OUT.with_suffix(".bin").write_bytes(bytes(rows))
    OUT.with_suffix(".json").write_text(
        json.dumps(
            {
                "model": "text-embedding-3-small",
                "dimensions": len(vectors[0]),
                "scale": SCALE,
                "text": "title. cuisine course. Made with <up to 12 ingredients>.",
                "texts_sha256": hashlib.sha256(json.dumps(texts, sort_keys=True).encode()).hexdigest(),
                "keys": list(texts),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}.bin/.json: {len(texts)} recipes, {len(rows) // 1024} KB")


if __name__ == "__main__":
    main()
