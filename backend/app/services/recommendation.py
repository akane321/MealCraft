from collections import Counter

from app.data.halal import needs_certification
from app.models.recipe import Recipe
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.meal_composition import meal_role_of
from app.planning.product_path import meals_of_the_day
from app.planning.recommendation_engine import CANDIDATE_LIMIT, RecipeRecommendationEngine
from app.repositories.recipe import RecipeRepository
from app.schemas.planning_v2 import structured
from app.schemas.product import GroceryEstimateResponse
from app.schemas.recommendation import (
    ExcludedRecipeResponse,
    RecipeRecommendationCollectionResponse,
    RecipeRecommendationRequest,
)


def _meat_without_certified_product(estimate: GroceryEstimateResponse) -> bool:
    """Whether a line that needs a certified product is to be bought and has none (at home or in the pantry: no)."""
    unmapped = set(estimate.unmapped_ingredients)
    return any(
        needs_certification(item.ingredient_name)
        and (
            item.ingredient_name in unmapped or (item.product is not None and item.product.halal_certified is not True)
        )
        for item in estimate.items
    )


class RecipeRecommendationService:
    def __init__(
        self,
        repository: RecipeRepository,
        grocery_estimator: GroceryEstimator,
        engine: RecipeRecommendationEngine | None = None,
    ) -> None:
        self.repository = repository
        self.grocery_estimator = grocery_estimator
        self.engine = engine or RecipeRecommendationEngine()

    def recommend(
        self,
        constraints: RecipeRecommendationRequest,
        *,
        deduct_pantry_from_cost: bool = True,
        recipes: list[Recipe] | None = None,
        priced_release_only: bool = False,
    ) -> RecipeRecommendationCollectionResponse:
        """Rank the catalog and keep the best CANDIDATE_LIMIT within budget, of each course for a composed meal.

        The planner cannot verify a plan containing an unpriced recipe. With
        `priced_release_only`, release recipes whose products are not all mapped are
        dropped before the limit, so they never crowd out plannable ones. Curated
        recipes always stay, as before.
        """
        if recipes is None:
            recipes = self.repository.list_for_recommendation()
        recommendations, excluded = self.engine.recommend(recipes, constraints)
        warnings: list[str] = []
        recipes_by_id = {recipe.id: recipe for recipe in recipes}
        enriched = []
        # A composed meal fills each role from its own courses. Kept as one list, the quickest mains crowded
        # out the rest: the 2026-10-02 walkthrough's 500 held 12 of its 178 soups.
        meals = meals_of_the_day(constraints)
        per_course = meals is not None
        # Meals of meal roles fill each role by its tag (ADR-0070): the quota is kept per meal role instead.
        by_tag = per_course and any(structured(roles) for _, roles in meals)
        kept: Counter = Counter()

        for recommendation in recommendations:
            recipe = recipes_by_id[recommendation.recipe.id]
            course = (meal_role_of(recipe) if by_tag else recipe.course or "main") if per_course else None
            if kept[course] == CANDIDATE_LIMIT:
                if per_course:
                    continue
                break
            estimation_constraints = (
                constraints if deduct_pantry_from_cost else constraints.model_copy(update={"available_ingredients": []})
            )
            estimate = self.grocery_estimator.estimate(recipe, estimation_constraints)
            if priced_release_only and recipe.release_version is not None and not estimate.complete:
                continue
            if constraints.requires_halal and _meat_without_certified_product(estimate):
                excluded.append(
                    ExcludedRecipeResponse(
                        id=recipe.id, slug=recipe.slug, title=recipe.title, reasons=["halal_requirement"]
                    )
                )
                continue
            for warning in estimate.warnings:
                if warning not in warnings:
                    warnings.append(warning)

            budget = constraints.budget_per_meal_sgd
            if budget is not None and estimate.within_budget is False:
                excluded.append(
                    ExcludedRecipeResponse(
                        id=recipe.id,
                        slug=recipe.slug,
                        title=recipe.title,
                        reasons=[
                            f"Estimated ingredient-use cost S${estimate.consumed_total_sgd:.2f} "
                            f"is above the S${budget:.2f} meal budget."
                        ],
                    )
                )
                continue

            reasons = list(recommendation.reasons)
            if estimate.consumed_total_sgd is not None:
                reasons.append(
                    f"Estimated ingredient-use cost is S${estimate.consumed_total_sgd:.2f}; "
                    f"buying the required packages costs S${estimate.purchase_total_sgd:.2f}."
                )
            kept[course] += 1
            enriched.append(
                recommendation.model_copy(
                    update={
                        "reasons": reasons,
                        "grocery_estimate": estimate,
                    }
                )
            )

        if constraints.pricing_mode == "fixture":
            warnings.append(
                "Stable fixture prices are shown for reproducible planning; select live pricing to query FairPrice."
            )
        if constraints.budget_per_meal_sgd is not None and any(
            item.grocery_estimate is not None and not item.grocery_estimate.complete for item in enriched
        ):
            warnings.append("Budget could not be enforced for recipes with incomplete product mappings.")

        excluded.sort(key=lambda item: item.id)

        return RecipeRecommendationCollectionResponse(
            recommendations=enriched,
            excluded=excluded,
            warnings=warnings,
        )
