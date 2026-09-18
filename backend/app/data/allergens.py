"""Which allergens the runtime catalog vouches for, and the one rule for applying them.

The catalog lists, for every ingredient, each allergen it contains out of a
fixed checked vocabulary (`data/ingredients/allergen-vocabulary.json`). An empty
list therefore means "checked, contains none of them". An allergen outside the
vocabulary was never checked, so its status is unknown for every ingredient, and
unknown is excluded rather than admitted (ADR-0024 section 3).
"""

import json
from collections.abc import Iterable
from functools import lru_cache

from app.core.paths import data_root

VOCABULARY_FILE = "ingredients/allergen-vocabulary.json"


@lru_cache
def checked_allergens() -> frozenset[str]:
    data = json.loads((data_root() / VOCABULARY_FILE).read_text(encoding="utf-8"))
    return frozenset(data["checked"])


def allergen_conflicts(
    requested: Iterable[str],
    contained: Iterable[str],
    checked: Iterable[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (present, unverifiable) for one recipe.

    `present` are requested allergens the recipe contains; `unverifiable` are
    requested allergens nobody checked for. Either being non-empty excludes it.
    """
    wanted = {item.lower() for item in requested}
    vocabulary = checked_allergens() if checked is None else {item.lower() for item in checked}
    present = sorted(wanted.intersection(item.lower() for item in contained))
    unverifiable = sorted(wanted.difference(vocabulary))
    return present, unverifiable


def conflict_reasons(present: list[str], unverifiable: list[str]) -> list[str]:
    reasons: list[str] = []
    if present:
        reasons.append(f"Contains selected allergen: {', '.join(present)}.")
    if unverifiable:
        reasons.append(f"Cannot confirm it is free of: {', '.join(unverifiable)}.")
    return reasons
