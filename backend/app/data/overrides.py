"""Console edits over the file-based catalog knowledge (ADR-0047 Data).

Ingredient aliases, Chinese names and the FairPrice product mapping are reviewed files under data/ that
the parser and the estimator read once and cache. An edit from the operations console is a
`catalog_overrides` row; this module holds the rows in memory and the readers lay them over what the
files say. The rows are loaded with the first request's session and again after every console edit.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.platform import CatalogOverride

logger = logging.getLogger(__name__)

# ponytail: per process; a console edit reaches other worker processes only when they restart.
_rows: dict[str, dict[str, Any]] = {}
_loaded = False


def overrides(kind: str) -> dict[str, Any]:
    """Console values of one kind by ingredient (normalized name)."""
    return _rows.get(kind, {})


def reload(database: Session) -> None:
    global _loaded
    fresh: dict[str, dict[str, Any]] = {}
    for row in database.scalars(select(CatalogOverride)):
        fresh.setdefault(row.kind, {})[row.key] = row.value
    _rows.clear()
    _rows.update(fresh)
    _loaded = True
    # The readers cache their merged view; imported here because they import this module.
    from app.agent.ingredient_matcher import catalog_aliases
    from app.planning.grocery_estimator import release_products
    from app.planning.recipe_similarity import chinese_words

    for cached in (catalog_aliases, release_products, chinese_words):
        cached.cache_clear()


def ensure_loaded(database: Session) -> None:
    """Load the rows once per process; before the migration, the files alone apply."""
    global _loaded
    if _loaded:
        return
    try:
        reload(database)
    except SQLAlchemyError:
        database.rollback()
        logger.warning("catalog_overrides could not be read; using the catalog files only", exc_info=True)
        _loaded = True
