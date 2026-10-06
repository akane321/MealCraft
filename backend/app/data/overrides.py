"""Console edits over the file-based catalog knowledge (ADR-0047 Data).

Ingredient aliases, Chinese names and the FairPrice product mapping are reviewed files under data/ that
the parser and the estimator read once and cache. An edit from the operations console is a
`catalog_overrides` row; this module holds the rows in memory and the readers lay them over what the
files say. The rows are loaded with the first request's session and again after every console edit.
"""

import logging
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.platform import CatalogOverride

logger = logging.getLogger(__name__)

# ponytail: per process; a console edit reaches other worker processes only when they restart.
_rows: dict[str, dict[str, Any]] = {}
_loaded = False
_load_failed = False
_load_lock = threading.Lock()


def overrides(kind: str) -> dict[str, Any]:
    """Console values of one kind by ingredient (normalized name)."""
    return _rows.get(kind, {})


def reload(database: Session) -> None:
    global _load_failed, _loaded
    fresh: dict[str, dict[str, Any]] = {}
    for row in database.scalars(select(CatalogOverride)):
        fresh.setdefault(row.kind, {})[row.key] = row.value
    _rows.clear()
    _rows.update(fresh)
    _loaded = True
    _load_failed = False
    # The readers cache their merged view; imported here because they import this module.
    from app.agent.ingredient_matcher import catalog_aliases
    from app.planning.grocery_estimator import release_products
    from app.planning.recipe_similarity import chinese_words

    for cached in (catalog_aliases, release_products, chinese_words):
        cached.cache_clear()


def _catalog_overrides_table_is_missing(error: SQLAlchemyError) -> bool:
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    message = str(original).lower()
    return sqlstate == "42P01" or ("no such table" in message and "catalog_overrides" in message)


def ensure_loaded(database: Session) -> bool:
    """Load the rows once per process; before the migration, the files alone apply."""
    global _load_failed, _loaded
    if _loaded:
        return True
    with _load_lock:
        if _loaded:
            return True
        try:
            reload(database)
        except SQLAlchemyError as error:
            database.rollback()
            if _catalog_overrides_table_is_missing(error):
                logger.warning("catalog_overrides is not available before its migration; using catalog files only")
                _loaded = True
                _load_failed = False
                return True
            if not _load_failed:
                logger.warning("catalog_overrides could not be read; retrying later", exc_info=True)
            else:
                logger.warning("catalog_overrides still could not be read; retrying later")
            _load_failed = True
            return False
        return True
