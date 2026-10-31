"""The halal rules of the scorers, from the one set of labels (`app.data.halal`; docs/evaluation/halal.md).

Unknown is never halal (ADR-0104): a line with no label, an `uncertain` label or no catalog ingredient at all fails
a halal household, as does a `not_halal` one. A meat line (`needs_certification`) fails unless a certified product
is bought, or, for a baseline that buys nothing, unless the snapshot holds a certified product for it.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.data.halal import halal_labels, needs_certification, product_certified


def required(episode: dict) -> bool:
    """Whether the episode's gold says the household needs halal food."""
    return bool(episode["gold"]["applicable_hard_constraints"].get("halal_required"))


def line_problem(ingredient_id: str | None, certified: Iterable[str]) -> str | None:
    """Why one ingredient line fails a halal household, or None when it passes.

    `certified` holds the ingredients that have a certified product to buy."""
    if ingredient_id is None:
        return "unmapped"
    label = halal_labels().get(ingredient_id)
    if label is None or label["status"] == "uncertain":
        return "uncertain"
    if label["status"] == "not_halal":
        return "not_halal"
    if needs_certification(ingredient_id) and ingredient_id not in set(certified):
        return "no certified product"
    return None


def bought_certified(shopping: Iterable[tuple[str, str | None]]) -> frozenset[str]:
    """Ingredients whose every purchased product is certified; (ingredient_id, product_id) pairs.

    A frozen id may be `<id>@<ingredient>` (a product shared by two ingredients): `product_certified` reads it."""
    products: dict[str, list[str | None]] = {}
    for ingredient_id, product_id in shopping:
        products.setdefault(ingredient_id, []).append(product_id)
    return frozenset(
        name
        for name, ids in products.items()
        if all(product_id is not None and product_certified(product_id) for product_id in ids)
    )
