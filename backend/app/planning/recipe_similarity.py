"""How close a catalog recipe is to what the household said they want instead ("fish", "来点辣的").

Used only to order replacement candidates that already passed every hard constraint; it never admits a
recipe the planner would reject. Vectors are precomputed (`scripts/embed_recipes.py`): unit-length,
int8-quantised rows in a raw file, one embedding call per request at run time.

The score is cosine similarity plus 0.05 per word the request shares with the recipe's title, cuisine or
ingredients. On the developer requests (`scripts/evaluate_replan_requests.py`) that picked what was asked
for in 80% of trials, against 71% for similarity alone, 55% for shared words alone and 10% for ignoring
the request, which is what the swap did before.
"""

import json
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.paths import find_repository_root
from app.models.recipe import Recipe

VECTORS = "data/recipes/embeddings-v1"
Embed = Callable[[list[str]], list[list[float]]]

# Words that ask for a change or name a day or meal, not what to eat instead.
_FILLER = re.compile(
    r"\b(?:can|could|would|you|we|i|i'd|id|me|my|please|pls|instead|of|for|on|at|the|a|an|to|it|be|have|"
    r"make|want|like|feel|something|anything|some|with|dinner|lunch|meal|dish|tonight|today|tomorrow|day|"
    r"replace|swap|change|switch|different|another|other|new|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"\d+)\b"
    r"|换成|换掉|换一个|换个|替换|换|改成|周[一二三四五六日天]|星期[一二三四五六日天]|今天|明天|第.天|"
    r"我想吃|想吃|我想|想要|来点|来个|有没有|吧|的|一下|晚饭|晚餐|那顿|这顿|吗|呢|[?？!！,，.。]",
    re.IGNORECASE,
)


def wanted(reason: str | None) -> str | None:
    """What the household described wanting, with the swap mechanics removed; None when nothing is left."""
    if not reason:
        return None
    rest = " ".join(_FILLER.sub(" ", reason).split())
    return rest if re.search(r"[a-zA-Z]{3,}|[一-鿿]", rest) else None


KEYWORD_WEIGHT = 0.05


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}|[一-鿿]", text.lower().replace("_", " ")))


def recipe_words(recipe: Recipe) -> set[str]:
    names = " ".join(item.ingredient.display_name for item in recipe.recipe_ingredients)
    return words(f"{recipe.title} {recipe.cuisine} {names}")


def recipe_key(recipe: Recipe) -> str:
    return recipe.external_id or f"slug:{recipe.slug}"


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict, dict[str, int], bytes] | None:
    base = find_repository_root(Path(__file__).parent) / VECTORS
    meta_path, rows_path = base.with_suffix(".json"), base.with_suffix(".bin")
    if not (meta_path.exists() and rows_path.exists()):
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return meta, {key: i for i, key in enumerate(meta["keys"])}, rows_path.read_bytes()


def catalog_embedder(api_key: str) -> Embed | None:
    """Embeds with the model and size the recipe vectors were made with, or None without them."""
    catalog = _catalog()
    if catalog is None:
        return None
    from langchain_openai import OpenAIEmbeddings

    meta = catalog[0]
    return OpenAIEmbeddings(model=meta["model"], dimensions=meta["dimensions"], api_key=api_key).embed_documents


class RecipeSimilarity:
    def __init__(self, embed: Embed | None) -> None:
        self.embed = embed

    def scores(self, reason: str | None, recipes: list[Recipe]) -> dict[int, float]:
        """Cosine similarity per recipe id; empty when there is nothing described, no vectors, or no call."""
        text, catalog = wanted(reason), _catalog()
        if text is None or catalog is None or self.embed is None:
            return {}
        meta, index, rows = catalog
        try:
            (query,) = self.embed([text])
        except Exception:  # noqa: BLE001 - a failed call leaves the swap to the ordinary score
            return {}
        size = meta["dimensions"]
        norm = sum(x * x for x in query) ** 0.5 or 1.0
        asked = words(text)
        result = {}
        for recipe in recipes:
            i = index.get(recipe_key(recipe))
            if i is None:
                continue
            row = [b - 256 if b > 127 else b for b in rows[i * size : (i + 1) * size]]
            dot = sum(q * b for q, b in zip(query, row, strict=True))
            cosine = dot / (norm * (sum(b * b for b in row) ** 0.5 or 1.0))
            result[recipe.id] = cosine + KEYWORD_WEIGHT * len(asked & recipe_words(recipe))
        return result
