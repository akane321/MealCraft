"""Freeze live YouTube candidates for a sample of catalog mains, so tutorial ranking can be labelled once
and every later ranking change measured offline against the same candidates.

    PYTHONPATH=backend python scripts/snapshot_tutorial_candidates.py

Needs YOUTUBE_API_KEY in .env. Each query form costs 39 searches, about 3,940 of the 10,000 daily quota
units, so a rerun only searches the forms the snapshot does not have yet. Half the dishes are developer
(ranking may be tuned on their labels), half held-out (read once, at the end).
"""

import json
import random
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.retrieval.tutorials import YouTubeDataApiProvider, build_tutorial_query

RELEASE = Path("data-engineering/data/release/v2.1/recipes.jsonl")
OUT = Path("data/evaluation/tutorials/candidates-v1.json")
SEED = 20260925
# Dishes per cuisine: weighted by how many mains the catalog has, with Singapore-relevant cuisines lifted.
QUOTA = {
    "chinese": 5,
    "american": 3,
    "thai": 3,
    "malaysian_singaporean": 3,
    "japanese": 2,
    "italian": 2,
    "korean": 2,
    "indian": 2,
    "filipino": 2,
    "vietnamese": 2,
    "indonesian": 2,
    "mexican": 1,
    "tex_mex": 1,
    "greek": 1,
    "middle_eastern": 1,
    "french": 1,
    "caribbean": 1,
    "north_african": 1,
    "british_irish": 1,
    "eastern_european": 1,
    "spanish_portuguese": 1,
    "southern_us": 1,
}


def query_forms(recipe: dict, ingredients: list[str]) -> dict[str, str]:
    """The shipped query, and the plain one people type; ranking work compares them on the same labels."""
    return {
        # The query shipped before ranking v2, spelled out so this snapshot stays reproducible.
        "v1": " ".join([recipe["title"], recipe["cuisine"], *ingredients[:3], "en", "cooking tutorial"]),
        "title": build_tutorial_query(recipe_title=recipe["title"]),
    }


def main() -> None:
    rng = random.Random(SEED)
    mains = [json.loads(line) for line in RELEASE.read_text(encoding="utf-8").splitlines()]
    mains = sorted((r for r in mains if r["course"] == "main"), key=lambda r: r["recipe_id"])
    picked = []
    for cuisine, count in QUOTA.items():
        pool = [r for r in mains if r["cuisine"] == cuisine]
        picked += rng.sample(pool, count)
    rng.shuffle(picked)
    settings = get_settings()
    provider = YouTubeDataApiProvider(
        api_key=settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else None,
        timeout_seconds=settings.youtube_timeout_seconds,
    )
    previous = (
        {d["recipe_id"]: d for d in json.loads(OUT.read_text(encoding="utf-8"))["dishes"]} if OUT.exists() else {}
    )
    dishes = []
    for i, recipe in enumerate(picked):
        ingredients = [item["canonical_name"] for item in recipe["ingredients"]]
        dish = previous.get(recipe["recipe_id"]) or {
            "recipe_id": recipe["recipe_id"],
            "title": recipe["title"],
            "cuisine": recipe["cuisine"],
            "ingredients": ingredients,
            "split": "developer" if i % 2 == 0 else "heldout",
            "queries": {},
            "candidates": [],
        }
        by_id = {c["video_id"]: c for c in dish["candidates"]}
        for form, query in query_forms(recipe, ingredients).items():
            if form in dish["queries"]:
                continue
            dish["queries"][form] = query
            for rank, c in enumerate(provider.search(query, limit=10), start=1):
                entry = by_id.setdefault(c.video_id, c.model_dump(mode="json", exclude={"source", "fetched_at"}))
                entry.setdefault("ranks", {})[form] = rank
        dish["candidates"] = list(by_id.values())
        dishes.append(dish)
        print(f"{i + 1:2}/{len(picked)} {len(dish['candidates']):2} candidates")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "version": "tutorial-candidates-v1",
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "release": "v2.1",
                "seed": SEED,
                "provider": "youtube-data-api-v1",
                "note": "Public YouTube metadata only. Labels live in labels-v1.json; held-out labels are read once.",
                "dishes": dishes,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
