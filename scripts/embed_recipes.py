"""Embed every catalog recipe once, for matching a household's words when they ask to swap a meal.

    PYTHONPATH="backend;scripts" python scripts/embed_recipes.py [--env-file ../.env] [--max-usd 0.50]

Needs OPENAI_API_KEY in .env, or in the one line of --env-file (never printed). About 18,400 short texts
(~700k tokens, under two US cents for all of them). Vectors are
unit-length, quantised to int8 and written as raw bytes (about 4.7 MB), so the runtime needs no numpy and
no vector database. Rerun when the catalog's recipes change: only recipes without a vector are embedded and
appended, so the vectors already in the file stay byte-identical (recipes whose text a later release changed
keep their old vector). The model and size must match the file's metadata, or it stops.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from embed_ingredients import embedder

RELEASE = Path("data-engineering/data/release/v3/recipes.jsonl")
CURATED = Path("data/recipes/recipes.json")
OUT = Path("data/recipes/embeddings-v1")  # .json (keys, model) and .bin (int8 rows)
SCALE = 127
USD_PER_MILLION_TOKENS = 0.02  # text-embedding-3-small


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
    parser = argparse.ArgumentParser(description="Embed the catalog recipes that have no vector yet.")
    parser.add_argument("--env-file", type=Path, help="read OPENAI_API_KEY from this file when it is not set")
    parser.add_argument("--max-usd", type=float, default=0.50, help="stop before calling if the estimate is higher")
    args = parser.parse_args()
    texts = recipe_texts()
    meta_path, bin_path = OUT.with_suffix(".json"), OUT.with_suffix(".bin")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    keys = meta.get("keys", [])
    rows = bytearray(bin_path.read_bytes()) if keys else bytearray()
    if keys and len(rows) != len(keys) * meta["dimensions"]:
        raise SystemExit("embeddings-v1.bin does not match the keys in embeddings-v1.json")
    missing = {key: text for key, text in texts.items() if key not in set(keys)}
    if not missing:
        print("every recipe already has a vector")
        return
    # A token is about four characters of English; count three to stay on the safe side.
    usd = sum(len(text) for text in missing.values()) / 3 * USD_PER_MILLION_TOKENS / 1e6
    print(f"{len(missing)} recipes to embed, about US${usd:.4f}")
    if usd > args.max_usd:
        raise SystemExit(f"estimate is over --max-usd {args.max_usd}")
    if args.env_file and not os.environ.get("OPENAI_API_KEY"):
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENAI_API_KEY":
                os.environ["OPENAI_API_KEY"] = value.strip().strip("\"'")
    client = embedder()
    if keys and (client.model, client.dimensions) != (meta["model"], meta["dimensions"]):
        raise SystemExit("the file was made with another model or size than embed_ingredients.embedder()")
    vectors = client.embed_documents(list(missing.values()), chunk_size=500)
    for vector in vectors:
        norm = sum(x * x for x in vector) ** 0.5 or 1.0
        rows += bytes((round(max(-1.0, min(1.0, x / norm)) * SCALE)) & 0xFF for x in vector)
    new_hash = hashlib.sha256(json.dumps(missing, sort_keys=True).encode()).hexdigest()
    bin_path.write_bytes(bytes(rows))
    new_meta = {
        "model": client.model,
        "dimensions": len(vectors[0]),
        "scale": SCALE,
        "text": "title. cuisine course. Made with <up to 12 ingredients>.",
        # Chained over the file's earlier hash and the texts embedded in this run.
        "texts_sha256": hashlib.sha256((meta.get("texts_sha256", "") + new_hash).encode()).hexdigest(),
        "keys": keys + list(missing),
    }
    meta_path.write_bytes((json.dumps(new_meta) + "\n").encode("utf-8"))
    print(f"added {len(missing)} recipes; {OUT}.bin/.json now hold {len(keys) + len(missing)}, {len(rows) // 1024} KB")


if __name__ == "__main__":
    main()
