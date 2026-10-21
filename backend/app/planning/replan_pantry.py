"""Temporary stock available after reserving the unchanged dishes' basket.

This is planning state, never a persisted claim that the household bought it.
Unknown quantities cannot provide a deduction.
"""

from app.planning.grocery_estimator import convert_quantity
from app.schemas.recommendation import AvailableIngredientInput


def remaining_stock(pantry, grocery, *, include_surplus=True):
    stock = {item.normalized_name: item.model_copy() for item in pantry}
    for line in grocery.items:
        item = stock.get(line.ingredient_name)
        if item is not None and item.quantity is not None:
            used = convert_quantity(line.pantry_deduction, line.unit, item.unit, line.ingredient_name)
            if used is None:
                # Cannot safely reserve this amount: do not offer it again.
                stock.pop(line.ingredient_name)
            else:
                item.quantity = max(0, item.quantity - used)
    for line in grocery.items if include_surplus else ():
        if line.product is None or line.excess_quantity is None or line.excess_quantity <= 0:
            continue
        name = line.ingredient_name
        unit = line.product.package_unit
        item = stock.get(name)
        if item is None or item.quantity is None or item.quantity <= 0:
            stock[name] = AvailableIngredientInput(normalized_name=name, quantity=line.excess_quantity, unit=unit)
        else:
            extra = convert_quantity(line.excess_quantity, unit, item.unit, name)
            if extra is not None:
                item.quantity += extra
    return [item for item in stock.values() if item.quantity is None or item.quantity > 0]
