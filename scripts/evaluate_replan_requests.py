"""Does the swapped-in dish match what the household asked for? Developer requests, checked on catalog facts.

    PYTHONPATH="backend;scripts" python scripts/evaluate_replan_requests.py

For each request, 30 seeded trials draw 100 catalog mains as the candidate pool (they stand for the
candidates that already passed the hard constraints) and each method picks one:
  ignore           - the request plays no part, as before this change (the pool's first candidate);
  keywords         - most words shared between the request and the recipe's title, cuisine, ingredients;
  embedding        - highest cosine similarity alone;
  shipped          - app/planning/recipe_similarity.py: similarity plus 0.05 per shared word.
A pick is a hit when the catalog says it is what was asked for (fish among its ingredients, cuisine
Japanese, ...). Trials whose pool holds no such recipe are left out. The requests were written by the
session that built the matcher, and "shipped" was chosen on them from three variants (a prompt prefix,
prefix plus words, words): a developer check, not evidence.
"""

import json
import random
from pathlib import Path
from types import SimpleNamespace

from app.planning import recipe_similarity
from app.planning.recipe_similarity import RecipeSimilarity, recipe_words, wanted, words
from embed_ingredients import embedder

RELEASE = Path("data-engineering/data/release/v2.1/recipes.jsonl")
TRIALS, POOL = 30, 100


def has(*ids: str):
    wanted_ids = set(ids)
    return lambda r: bool(
        wanted_ids & {i["canonical_ingredient_id"].removeprefix("ING_").lower() for i in r["ingredients"]}
    )


def cuisine(*names: str):
    return lambda r: r["cuisine"] in names


def titled(*title_words: str):
    return lambda r: any(w in r["title"].lower() for w in title_words)


def soup(r: dict) -> bool:
    return r["course"] == "soup" or "soup" in r["title"].lower()


FISH = has(
    "salmon", "cod", "tuna", "fish_fillet", "hake", "halibut", "trout", "catfish", "sardine", "anchovy",
    "swordfish", "milkfish", "red_snapper", "smoked_haddock", "salt_cod",
)  # fmt: skip
NOODLES = has(
    "rice_noodles", "egg_noodles", "udon_noodles", "soba_noodles", "ramen", "cellophane_noodles",
    "pancit_canton", "somyeon", "sweet_potato_noodles", "shirataki_noodles", "chow_mein_noodles",
)  # fmt: skip
SPICY = has(
    "chili_pepper", "chili_powder", "cayenne", "gochujang", "gochugaru", "sambal_oelek", "sriracha", "jalapeno",
    "chili_paste", "hot_sauce", "habanero_pepper", "scotch_bonnet", "green_chili", "chipotle_pepper",
    "chili_garlic_sauce", "chili_oil",
)  # fmt: skip
REQUESTS = [
    ("Can Wednesday be fish instead?", FISH),
    ("换成牛肉的", has("beef", "ground_beef", "beef_steak", "corned_beef")),
    ("I'd like noodles on Friday", NOODLES),
    ("something Japanese please", cuisine("japanese")),
    ("来点辣的", SPICY),
    ("a vegetarian dinner please", lambda r: "vegetarian" in r["dietary_tags"]),
    ("I feel like curry", titled("curry")),
    ("soup tonight", soup),
    ("swap Tuesday for a pasta dish", has("pasta", "macaroni", "orzo", "gnocchi", "cheese_tortellini")),
    ("我想吃日本菜", cuisine("japanese")),
    ("有没有豆腐的", has("tofu")),
    ("prawns please", has("shrimp")),
    ("chicken instead", has("chicken", "chicken_breast", "chicken_thigh", "chicken_wings", "cooked_chicken")),
    ("Indian food on Saturday", cuisine("indian")),
    ("换成汤", soup),
    ("Mexican night", cuisine("mexican", "tex_mex")),
    ("something with rice", has("rice", "brown_rice", "glutinous_rice", "wild_rice")),
    ("Thai please", cuisine("thai")),
    ("Korean style", cuisine("korean")),
    ("想吃面", NOODLES),
]
METHODS = ("ignore", "keywords", "embedding", "shipped")


def as_recipe(i: int, r: dict) -> SimpleNamespace:
    """The fields recipe_similarity reads from a Recipe row."""
    ingredients = [
        SimpleNamespace(ingredient=SimpleNamespace(display_name=x["canonical_name"])) for x in r["ingredients"]
    ]
    return SimpleNamespace(
        id=i,
        external_id=r["recipe_id"],
        slug="",
        title=r["title"],
        cuisine=r["cuisine"],
        recipe_ingredients=ingredients,
    )


def best(pool: list[int], score: dict[int, float]) -> int:
    """The highest-scoring candidate; ties go to the earlier one in the pool."""
    return max(pool, key=lambda i: (score.get(i, -1.0), -pool.index(i)))


def main() -> None:
    mains = [
        r for line in RELEASE.read_text(encoding="utf-8").splitlines() if (r := json.loads(line))["course"] == "main"
    ]
    recipes = [as_recipe(i, r) for i, r in enumerate(mains)]
    client = embedder()
    cache: dict[str, list[float]] = {}

    def embed(texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in cache]
        if missing:
            cache.update(zip(missing, client.embed_documents(missing), strict=True))
        return [cache[t] for t in texts]

    similarity = RecipeSimilarity(embed)
    rng = random.Random(20260925)
    totals, counted = dict.fromkeys(METHODS, 0), 0
    print(f"{'request':34} {'trials':>6} " + " ".join(f"{m:>9}" for m in METHODS))
    for request, check in REQUESTS:
        asked = words(wanted(request) or "")
        shipped = similarity.scores(request, recipes)
        weight, recipe_similarity.KEYWORD_WEIGHT = recipe_similarity.KEYWORD_WEIGHT, 0.0
        cosine = similarity.scores(request, recipes)
        recipe_similarity.KEYWORD_WEIGHT = weight
        hits, feasible = dict.fromkeys(METHODS, 0), 0
        for _ in range(TRIALS):
            pool = rng.sample(range(len(mains)), POOL)
            if not any(check(mains[i]) for i in pool):
                continue
            feasible += 1

            picks = {
                "ignore": pool[0],
                "keywords": best(pool, {i: len(asked & recipe_words(recipes[i])) for i in pool}),
                "embedding": best(pool, cosine),
                "shipped": best(pool, shipped),
            }
            for method, i in picks.items():
                hits[method] += check(mains[i])
        counted += feasible
        for method in METHODS:
            totals[method] += hits[method]
        print(f"{request:34} {feasible:>6} " + " ".join(f"{hits[m]:>9}" for m in METHODS))
    print(f"\n{'all requests':34} {counted:>6} " + " ".join(f"{totals[m] / counted:>9.0%}" for m in METHODS))


if __name__ == "__main__":
    main()
