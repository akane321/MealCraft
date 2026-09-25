"""Ask a model, once, for the other names people use for each catalog ingredient.

    PYTHONPATH="backend;scripts" python scripts/generate_ingredient_aliases.py

The aliases only feed the embedding text behind ingredient *suggestions*, which the household confirms;
they never map a word to an ingredient on their own. They are model output and are kept as such.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from embed_ingredients import catalog_names
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

OUT = Path("data/ingredients/aliases-v1.json")
BATCH = 60


class Entry(BaseModel):
    id: str
    aliases: list[str]


class Batch(BaseModel):
    items: list[Entry]


PROMPT = """For each grocery ingredient below, list up to six other names a home cook might use for
exactly the same ingredient: British and American English names, names used in Singapore and Malaysia
(English, Malay, Hokkien or Cantonese romanisation), and the usual Simplified Chinese name. Only names
for the same thing, never a related product, a dish, a brand or a broader category. An empty list is
fine when there is no other common name. Return every id exactly as given.

{rows}"""


def main() -> None:
    settings = get_settings()
    model = ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), model=settings.openai_model, temperature=0
    ).with_structured_output(Batch, method="json_schema")
    names = catalog_names()
    ids = list(names)
    aliases: dict[str, list[str]] = {}
    for start in range(0, len(ids), BATCH):
        chunk = ids[start : start + BATCH]
        rows = "\n".join(f"{i}: {names[i]}" for i in chunk)
        result = model.invoke(PROMPT.format(rows=rows))
        for entry in result.items:
            if entry.id in names:
                aliases[entry.id] = [a.strip() for a in entry.aliases if a.strip()][:6]
        print(f"{min(start + BATCH, len(ids))}/{len(ids)}")
    missing = [i for i in ids if i not in aliases]
    OUT.write_text(
        json.dumps(
            {
                "model": settings.openai_model,
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "note": "Model-generated, not reviewed. Used only in the embedding text for ingredient suggestions.",
                "missing": missing,
                "aliases": dict(sorted(aliases.items())),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}: {len(aliases)} ingredients, {len(missing)} missing")


if __name__ == "__main__":
    main()
