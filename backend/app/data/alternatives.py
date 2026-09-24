"""Recipe lines that allow either of two ingredients, and the options each one allows.

Release v2.1 maps a line like "1 lb. ground beef or turkey" to one combined
ingredient (`beef_or_turkey`) because a line has one ingredient id. The options
live in `data/ingredients/alternatives.json`; the release importer copies them
onto the combined ingredient, and the planner picks one per household
(`app/planning/alternatives.py`).
"""

from __future__ import annotations

import json
from functools import cache

from app.core.paths import data_root


@cache
def options() -> dict[str, tuple[str, ...]]:
    """Combined ingredient -> its options, in the order most recipes write them."""
    document = json.loads((data_root() / "ingredients/alternatives.json").read_text(encoding="utf-8"))
    return {name: tuple(entry["options"]) for name, entry in document["alternatives"].items()}
