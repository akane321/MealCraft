"""The other retailers' reviewed mappings (docs/design/cold-storage.md, docs/design/redmart.md,
docs/design/manual-prices.md).

FairPrice stays the main store. The second stores, Cold Storage then RedMart, fill only the ingredients the stores
before them lack; last come the prices a person recorded by hand ("manual"). Each mapping is a snapshot built by
`data-engineering/scripts/capture_<store>_snapshot.py` (the manual one by `manual_prices.py`), in the shape of
FairPrice's, with the operations console's changes laid over it.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Literal

from app.core.paths import data_root
from app.data.overrides import overrides
from app.schemas.product import ProductResponse, Retailer

COLD_STORAGE_SNAPSHOT_FILE = "products/cold-storage-v1-snapshot.json"
REDMART_SNAPSHOT_FILE = "products/redmart-v1-snapshot.json"
MANUAL_SNAPSHOT_FILE = "products/manual-v1-snapshot.json"
# A fill layer: a store, or the prices recorded by hand (whose products each name their platform).
SecondStore = Literal["cold_storage", "redmart", "manual"]
# The fill order: a later layer is used only when every earlier one (FairPrice first) has no product in stock.
SECOND_STORES: tuple[SecondStore, ...] = ("cold_storage", "redmart", "manual")

_fairprice_only: ContextVar[bool] = ContextVar("fairprice_only", default=False)


def _load_snapshot(relative_path: str) -> dict[str, dict]:
    path = data_root() / relative_path
    if not path.exists():
        return {}
    ingredients = json.loads(path.read_text(encoding="utf-8"))["ingredients"]
    # A price is whole cents, and the planner refuses anything else (see `release_snapshot`).
    for entry in ingredients.values():
        entry.setdefault("status", "mapped")  # the hand-recorded sheet's export need not carry one
        for product in entry.get("products", []):
            product["price_sgd"] = round(product["price_sgd"], 2)
    return ingredients


@lru_cache
def cold_storage_snapshot() -> dict[str, dict]:
    """The reviewed Cold Storage mapping as the file has it, by normalized ingredient name; absent means none."""
    return _load_snapshot(COLD_STORAGE_SNAPSHOT_FILE)


@lru_cache
def redmart_snapshot() -> dict[str, dict]:
    """The reviewed RedMart mapping as the file has it, by normalized ingredient name; absent means none."""
    return _load_snapshot(REDMART_SNAPSHOT_FILE)


@lru_cache
def manual_snapshot() -> dict[str, dict]:
    """The prices recorded by hand (`manual_prices.py export`), by normalized ingredient name; absent means none."""
    return _load_snapshot(MANUAL_SNAPSHOT_FILE)


def store_snapshot(store: SecondStore) -> dict[str, dict]:
    loaders: dict[str, Callable[[], dict[str, dict]]] = {
        "cold_storage": cold_storage_snapshot,
        "redmart": redmart_snapshot,
        "manual": manual_snapshot,
    }
    return loaders[store]()


def store_products(store: SecondStore) -> dict[str, dict]:
    """A second store's mapping in use: the file with the console's changes, a removed entry left out; {} inside
    `fairprice_only`.

    ponytail: merged on every call (a few hundred entries), so a console edit needs no cache to clear.
    """
    if _fairprice_only.get():
        return {}
    merged = {**store_snapshot(store), **overrides(f"product_mapping:{store}")}
    return {name: entry for name, entry in merged.items() if entry["status"] != "removed"}


def cold_storage_products() -> dict[str, dict]:
    return store_products("cold_storage")


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
    if product.source == "manual":
        return product.retailer or "other"  # the platform it was recorded from
    return product.source if product.source in SECOND_STORES else "fairprice"
