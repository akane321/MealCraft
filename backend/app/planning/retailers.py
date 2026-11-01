"""The second retailer's reviewed mapping (docs/design/cold-storage.md).

FairPrice stays the main store: Cold Storage fills only the ingredients FairPrice lacks. Its mapping is a
snapshot built by `data-engineering/scripts/capture_cold_storage_snapshot.py`, in the shape of FairPrice's,
with the operations console's changes laid over it.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from app.core.paths import data_root
from app.data.overrides import overrides
from app.schemas.product import ProductResponse, Retailer

COLD_STORAGE_SNAPSHOT_FILE = "products/cold-storage-v1-snapshot.json"
COLD_STORAGE_OVERRIDE_KIND = "product_mapping:cold_storage"

_fairprice_only: ContextVar[bool] = ContextVar("fairprice_only", default=False)


@lru_cache
def cold_storage_snapshot() -> dict[str, dict]:
    """The reviewed Cold Storage mapping as the file has it, by normalized ingredient name; absent means none."""
    path = data_root() / COLD_STORAGE_SNAPSHOT_FILE
    if not path.exists():
        return {}
    ingredients = json.loads(path.read_text(encoding="utf-8"))["ingredients"]
    # A price is whole cents, and the planner refuses anything else (see `release_snapshot`).
    for entry in ingredients.values():
        for product in entry.get("products", []):
            product["price_sgd"] = round(product["price_sgd"], 2)
    return ingredients


def cold_storage_products() -> dict[str, dict]:
    """The mapping in use: the file with the console's changes, a removed entry left out; {} inside `fairprice_only`.

    ponytail: merged on every call (a few hundred entries), so a console edit needs no cache to clear.
    """
    if _fairprice_only.get():
        return {}
    merged = {**cold_storage_snapshot(), **overrides(COLD_STORAGE_OVERRIDE_KIND)}
    return {name: entry for name, entry in merged.items() if entry["status"] != "removed"}


def is_fairprice_only() -> bool:
    """Whether the caller plans as if FairPrice were the only store; a cache of what can be priced keys on this."""
    return _fairprice_only.get()


@contextmanager
def fairprice_only() -> Iterator[None]:
    """Plan and price as if FairPrice were the only store: the frozen evaluation's catalog (until the 11-07 freeze)."""
    token = _fairprice_only.set(True)
    try:
        yield
    finally:
        _fairprice_only.reset(token)


def retailer_of(product: ProductResponse) -> Retailer:
    return "cold_storage" if product.source == "cold_storage" else "fairprice"
