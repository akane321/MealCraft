"""Project recipe details with explicit meal eligibility and nutrition basis."""

from dataclasses import dataclass

from pydantic import ValidationError

from app.planning.input_audit import nonfinite_issues
from app.schemas.planning_v2 import MealType, PlanningRecipeCandidate
from app.schemas.recipe import RecipeDetailResponse


@dataclass(frozen=True)
class RecipeInputResult:
    candidate: PlanningRecipeCandidate | None
    source: RecipeDetailResponse
    issues: tuple[str, ...]


def recipe_input(
    recipe: RecipeDetailResponse, *, allowed_meal_types: tuple[MealType, ...], nutrition_basis: str
) -> RecipeInputResult:
    """Keep source serving quantities; the planner scales them exactly once.

    Legacy `meal_type` and nutrition fields do not encode V2 eligibility or basis.
    The caller must supply those facts; this function does not establish them.
    """
    if nutrition_basis != "per_serving":
        raise ValueError("An explicit per_serving nutrition basis is required")
    if not allowed_meal_types or any(m not in ("breakfast", "lunch", "dinner", "snack") for m in allowed_meal_types):
        raise ValueError("Explicit V2 meal eligibility is required")
    source = recipe.model_copy(deep=True)
    numeric = nonfinite_issues(source.model_dump())
    if numeric:
        return RecipeInputResult(None, source, tuple(f"nonfinite:{i.path}" for i in numeric))
    data = dict(
        recipe_id=source.slug,
        title=source.title,
        servings=source.servings,
        allowed_meal_types=sorted(set(allowed_meal_types)),
        total_time_minutes=source.total_time_minutes,
        dietary_tags=list(source.dietary_tags),
        allergens=sorted({allergen for i in source.ingredients for allergen in i.allergens}),
        ingredients=[
            dict(ingredient_id=i.normalized_name, quantity=i.quantity, unit=i.unit) for i in source.ingredients
        ],
        nutrients_per_serving=source.nutrition.model_dump(),
        cuisine=source.cuisine,
    )
    blank = []
    if not source.slug.strip():
        blank.append("blank_recipe_id")
    for index, item in enumerate(source.ingredients):
        if not item.normalized_name.strip():
            blank.append(f"blank_ingredient_id:{index}")
        if item.unit is not None and not item.unit.strip():
            blank.append(f"blank_ingredient_unit:{index}")
        if any(not allergen.strip() for allergen in item.allergens):
            blank.append(f"blank_allergen:{index}")
    if blank:
        return RecipeInputResult(None, source, tuple(sorted(blank)))
    try:
        candidate = PlanningRecipeCandidate.model_validate(data)
    except ValidationError as exc:
        issues = tuple(sorted({"invalid:" + ".".join(map(str, e["loc"])) for e in exc.errors()}))
        return RecipeInputResult(None, source, issues)
    return RecipeInputResult(candidate, source, ())
