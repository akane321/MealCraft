"""Embed every catalog ingredient once, for the agent's ingredient suggestions.

    PYTHONPATH=backend python scripts/embed_ingredients.py

Needs OPENAI_API_KEY in .env. About 720 short names: a few thousand tokens, well under one US cent.
Rerun when the catalog's ingredients change; the file records which names it was built from.
"""

import hashlib
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.data.release_v2 import normalized_name
from langchain_openai import OpenAIEmbeddings

MODEL, DIMENSIONS = "text-embedding-3-small", 256
OUT = Path("data/ingredients/embeddings-v1.json")
ALIASES = Path("data/ingredients/aliases-v1.json")


def catalog_names() -> dict[str, str]:
    """Runtime ingredient id -> display name: the release's ingredients plus the curated recipes' own."""
    names = {}
    for line in Path("data-engineering/data/release/v2.1/ingredients.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        names[normalized_name(record["ingredient_id"])] = record["canonical_name"]
    for record in json.loads(Path("data/ingredients/ingredients.json").read_text(encoding="utf-8")):
        names.setdefault(record["normalized_name"], record["display_name"])
    return dict(sorted(names.items()))


def embedder() -> OpenAIEmbeddings:
    key = get_settings().openai_api_key
    if key is None:
        sys.exit("OPENAI_API_KEY is not set")
    return OpenAIEmbeddings(model=MODEL, dimensions=DIMENSIONS, api_key=key.get_secret_value())


def embedding_texts(names: dict[str, str]) -> dict[str, str]:
    """The display name, plus the model-generated other names when that file exists."""
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))["aliases"] if ALIASES.exists() else {}
    return {
        key: f"{name}; also called {', '.join(aliases[key])}" if aliases.get(key) else name
        for key, name in names.items()
    }


def main() -> None:
    names = catalog_names()
    texts = embedding_texts(names)
    vectors = embedder().embed_documents(list(texts.values()))
    OUT.write_text(
        json.dumps(
            {
                "model": MODEL,
                "dimensions": DIMENSIONS,
                "text": "display name; also called <aliases-v1.json>",
                "texts_sha256": hashlib.sha256(
                    json.dumps(texts, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
                "vectors": {key: [round(x, 5) for x in vector] for key, vector in zip(names, vectors, strict=True)},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}: {len(names)} ingredients")


if __name__ == "__main__":
    main()
