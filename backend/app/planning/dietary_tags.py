"""Close dietary tags over the entailments that hold by definition.

A requirement for `vegetarian` matched only recipes literally carrying that tag,
so every vegan recipe was filtered out despite being vegetarian by definition.
On the committed catalog that meant a vegetarian household saw 8 recipes instead
of 20, and the 12 it lost were not marginal - they were the ones a vegan cook
would have written.

The table is data, not code, so a new entailment is a data change with a
recorded reason rather than an edit here. `data/recipes/dietary-tag-implications.json`
carries the admission rule: a pair belongs only when the entailment is true by
definition of the terms. Anything weaker becomes an implicit rule the user
cannot see and did not ask for, which is a worse failure than the omission it
fixes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.paths import repository_root

IMPLICATIONS_RELATIVE = Path("data/recipes/dietary-tag-implications.json")


class DietaryImplicationCycle(ValueError):
    """Raised when the table entails a cycle, which has no closure."""


@lru_cache(maxsize=1)
def load_implications() -> dict[str, frozenset[str]]:
    payload = json.loads((repository_root() / IMPLICATIONS_RELATIVE).read_text(encoding="utf-8"))
    return {tag: frozenset(entry["entails"]) for tag, entry in (payload.get("implications") or {}).items()}


def expand_tags(tags: object, implications: dict[str, frozenset[str]] | None = None) -> frozenset[str]:
    """Return the tags a recipe satisfies, including everything they entail.

    Closes transitively, so `a -> b` and `b -> c` need not be written as
    `a -> b, c`. A cycle raises rather than looping: an entailment table that
    contradicts itself is a data error, and silently ignoring it would make the
    filter behave differently from what the table says.
    """
    table = load_implications() if implications is None else implications
    resolved: set[str] = set()
    frontier = [str(tag) for tag in tags]
    steps = 0
    limit = (len(frontier) + len(table)) * (len(table) + 1) + 1
    while frontier:
        steps += 1
        if steps > limit:
            raise DietaryImplicationCycle("Dietary tag implications do not terminate; the table contains a cycle.")
        tag = frontier.pop()
        if tag in resolved:
            continue
        resolved.add(tag)
        frontier.extend(table.get(tag, ()))
    return frozenset(resolved)


def satisfies(required: object, recipe_tags: object) -> bool:
    """Whether a recipe's tags meet every required tag, entailments included."""
    return set(str(tag) for tag in required).issubset(expand_tags(recipe_tags))
