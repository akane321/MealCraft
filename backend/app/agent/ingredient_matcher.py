"""Suggest catalog ingredients for a word the household used that the planner cannot check.

The agent writes constraints in catalog ids; a word outside them (`cooking wine`, `taugeh`, `葱`) is set
aside and asked about (`align_to_vocabulary`). This module only makes that question answerable with one
tap: it proposes the closest catalog ingredients. It never applies one — near in meaning is not the same
thing (peanut oil is not peanut), so the household always chooses.

Embedding similarity needs the catalog's vectors (`scripts/embed_ingredients.py`) and one embedding call
per term; spelling similarity needs nothing and is the fallback when either is missing or the call fails.
On the developer terms embedding found an acceptable id in the four offered far more often than spelling,
and fusing the two did worse than embedding alone (`scripts/evaluate_ingredient_matching.py`).
"""

import json
import math
import re
import unicodedata
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from app.core.paths import find_repository_root
from app.data.overrides import overrides

VECTORS = "data/ingredients/embeddings-v1.json"
ALIASES = "data/ingredients/aliases-v1.json"  # model-generated other names, suggestions only
ZH_ALIASES = "data/ingredients/aliases-zh-v1.json"  # model-generated Chinese names, suggestions only
Embed = Callable[[list[str]], list[list[float]]]


def fold(text: str) -> str:
    """Lower case, accents removed, underscores as spaces: jalapeño and jalapeno_pepper meet."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode() or text
    return re.sub(r"[_\s]+", " ", text.casefold()).strip()


def spelling_score(term: str, name: str) -> float:
    a, b = fold(term), fold(name)
    if not a or not b:
        return 0.0
    words_a, words_b = set(a.split()), set(b.split())
    overlap = len(words_a & words_b) / len(words_a | words_b)
    return max(SequenceMatcher(None, a, b).ratio(), overlap)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class IngredientMatcher:
    def __init__(
        self,
        names: dict[str, str],
        *,
        vectors: dict[str, list[float]] | None = None,
        embed: Embed | None = None,
        aliases: dict[str, list[str]] | None = None,
        mode: str = "embedding",
    ) -> None:
        """names: catalog id -> display name. mode: "embedding" (spelling when it cannot run) or "spelling"."""
        self.names = names
        self.vectors = {key: value for key, value in (vectors or {}).items() if key in names}
        self.embed = embed
        self.mode = mode
        # A word that is exactly an ingredient's name or listed other name goes first: a one-word query
        # (`rocket`, `香菜`) embeds poorly against a name-plus-aliases text even when the alias is there.
        self.exact: dict[str, list[str]] = {}
        for key, name in names.items():
            for word in {fold(key), fold(name), *(fold(alias) for alias in (aliases or {}).get(key, []))}:
                self.exact.setdefault(word, []).append(key)

    def _by_spelling(self, term: str) -> list[str]:
        scored = {
            ingredient: max(spelling_score(term, name), spelling_score(term, ingredient))
            for ingredient, name in self.names.items()
        }
        return sorted(scored, key=lambda ingredient: (-scored[ingredient], ingredient))

    def _by_embedding(self, term: str) -> list[str] | None:
        if not (self.embed and self.vectors):
            return None
        try:
            (query,) = self.embed([term])
        except Exception:  # noqa: BLE001 - a failed call only loses the suggestion, never the turn
            return None
        scored = {ingredient: cosine(query, vector) for ingredient, vector in self.vectors.items()}
        return sorted(scored, key=lambda ingredient: (-scored[ingredient], ingredient))

    def suggest(self, term: str, *, limit: int = 4) -> list[str]:
        if self.mode == "spelling":
            ranked = self._by_spelling(term)
        else:
            # No vectors, no key, or the call failed: spelling still helps.
            ranked = self._by_embedding(term) or self._by_spelling(term)
        exact = sorted(self.exact.get(fold(term), []))
        return list(dict.fromkeys([*exact, *ranked]))[:limit]


@lru_cache(maxsize=1)
def _vector_file() -> dict:
    path = find_repository_root(Path(__file__).parent) / VECTORS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def catalog_vectors() -> dict[str, list[float]]:
    return _vector_file().get("vectors", {})


def catalog_embedder(api_key: str) -> Embed | None:
    """Embeds a term with the very model and size the catalog vectors were made with, or None without them."""
    meta = _vector_file()
    if not meta:
        return None
    from langchain_openai import OpenAIEmbeddings

    client = OpenAIEmbeddings(
        model=meta["model"], dimensions=meta["dimensions"], api_key=api_key, timeout=10, max_retries=1
    )
    return client.embed_documents


@lru_cache(maxsize=2)
def alias_file(name: str) -> dict[str, list[str]]:
    """One alias file as it is on disk: catalog id -> names."""
    path = find_repository_root(Path(__file__).parent) / name
    return json.loads(path.read_text(encoding="utf-8"))["aliases"] if path.exists() else {}


def names_of(kind: str) -> dict[str, list[str]]:
    """Other names ("aliases") or Chinese names ("zh_names") per catalog id, with the console's edits."""
    return {**alias_file(ALIASES if kind == "aliases" else ZH_ALIASES), **overrides(kind)}


@lru_cache(maxsize=1)
def catalog_aliases() -> dict[str, list[str]]:
    """Other names per catalog id: aliases-v1.json, plus the Chinese names (a short Chinese word such as
    茄子 embeds poorly, so an exact name is what finds it)."""
    merged: dict[str, list[str]] = {}
    for kind in ("aliases", "zh_names"):
        for key, values in names_of(kind).items():
            merged[key] = list(dict.fromkeys([*merged.get(key, []), *values]))
    return merged
