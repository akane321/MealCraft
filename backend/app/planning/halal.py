"""The one halal eligibility rule of the planner (docs/design/halal.md, ADR-0104).

With `requires_halal` a recipe is accepted when its status is `halal`, or `needs_certification` and every line that
needs a certified product has at least one available certified product option in the problem. Everything else
(`not_halal`, `uncertain`, no label) is rejected: unknown is never halal.
"""

from app.data.halal import needs_certification


def product_allowed(problem, product) -> bool:
    """A halal household's meat line takes only a certified product; every other product is unaffected."""
    return (
        not problem.requires_halal or product.halal_certified is True or not needs_certification(product.ingredient_id)
    )


def halal_ok(recipe, problem) -> bool:
    """Whether `recipe` may be served to a halal household under `problem`.

    `problem` is a FinalPlanningProblem. The recommendation engine runs before any product is chosen and passes the
    request, which has no `products`; it only screens the status, and the planning problem built afterwards (with
    its certified options) applies the full rule.
    """
    if not problem.requires_halal or recipe.halal_status == "halal":
        return True
    if recipe.halal_status != "needs_certification":
        return False
    products = getattr(problem, "products", None)
    if products is None:
        return True
    certified = {item.ingredient_id for item in products if item.available and item.halal_certified}
    return all(
        line.ingredient_id in certified for line in recipe.ingredients if needs_certification(line.ingredient_id)
    )
