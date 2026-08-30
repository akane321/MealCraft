from dataclasses import dataclass

from app.models.recipe import Recipe
from app.schemas.recipe import RecipeListItemResponse
from app.schemas.recommendation import (
    ExcludedRecipeResponse,
    RecipeRecommendationRequest,
    RecipeRecommendationResponse,
    RecommendationScoreBreakdown,
)

FLEXIBLE_SODIUM_BENCHMARK_MG = 700.0
FLEXIBLE_SODIUM_UPPER_RANGE_MG = 1400.0
FLEXIBLE_SUGAR_BENCHMARK_G = 12.0
FLEXIBLE_SUGAR_UPPER_RANGE_G = 30.0
LOWER_CALORIE_BENCHMARK_KCAL = 600.0
LOWER_CALORIE_UPPER_RANGE_KCAL = 1000.0


@dataclass(frozen=True)
class ScoredRecipe:
    recipe: Recipe
    response: RecipeRecommendationResponse


class RecipeRecommendationEngine:
    def recommend(
        self,
        recipes: list[Recipe],
        constraints: RecipeRecommendationRequest,
    ) -> tuple[list[RecipeRecommendationResponse], list[ExcludedRecipeResponse]]:
        scored: list[ScoredRecipe] = []
        excluded: list[ExcludedRecipeResponse] = []

        for recipe in recipes:
            exclusion_reasons = self._exclusion_reasons(recipe, constraints)
            if exclusion_reasons:
                excluded.append(
                    ExcludedRecipeResponse(
                        id=recipe.id,
                        slug=recipe.slug,
                        title=recipe.title,
                        reasons=exclusion_reasons,
                    )
                )
                continue

            response = self._score_recipe(recipe, constraints)
            scored.append(ScoredRecipe(recipe=recipe, response=response))

        scored.sort(key=lambda item: (-item.response.total_score, item.recipe.id))
        excluded.sort(key=lambda item: item.id)
        return [item.response for item in scored], excluded

    def _exclusion_reasons(self, recipe: Recipe, constraints: RecipeRecommendationRequest) -> list[str]:
        reasons: list[str] = []
        ingredient_names = {item.ingredient.normalized_name for item in recipe.recipe_ingredients}
        recipe_allergens = {
            item.ingredient.allergen.lower() for item in recipe.recipe_ingredients if item.ingredient.allergen
        }

        allergen_matches = sorted(recipe_allergens.intersection(constraints.allergens))
        if allergen_matches:
            reasons.append(f"Contains selected allergen: {', '.join(allergen_matches)}.")

        excluded_matches = sorted(ingredient_names.intersection(constraints.excluded_ingredients))
        if excluded_matches:
            reasons.append(f"Contains excluded ingredient: {', '.join(excluded_matches)}.")

        if recipe.total_time_minutes > constraints.max_cooking_time_minutes:
            reasons.append(
                f"Requires {recipe.total_time_minutes} minutes, above the "
                f"{constraints.max_cooking_time_minutes}-minute limit."
            )

        recipe_tags = set(recipe.dietary_tags)
        for preference in constraints.dietary_preferences:
            if not self._satisfies_dietary_preference(preference, recipe_tags):
                reasons.append(f"Does not satisfy the {preference} requirement.")

        sodium_limit = constraints.max_sodium_mg_per_meal
        if sodium_limit is not None and float(recipe.nutrition.sodium_mg) > sodium_limit:
            reasons.append(
                f"Contains {float(recipe.nutrition.sodium_mg):.0f} mg sodium per serving, "
                f"above the user-entered {sodium_limit:.0f} mg limit."
            )

        return reasons

    @staticmethod
    def _satisfies_dietary_preference(preference: str, recipe_tags: set[str]) -> bool:
        if preference == "vegetarian":
            return bool({"vegetarian", "vegan"}.intersection(recipe_tags))
        if preference == "dairy-free" and "vegan" in recipe_tags:
            return True
        return preference in recipe_tags

    def _score_recipe(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
    ) -> RecipeRecommendationResponse:
        reasons = [
            f"Fits the {constraints.max_cooking_time_minutes}-minute limit ({recipe.total_time_minutes} minutes)."
        ]
        time_score = self._time_score(recipe.total_time_minutes, constraints.max_cooking_time_minutes)
        nutrition_score = self._nutrition_score(recipe, constraints, reasons)
        pantry_score = self._pantry_score(recipe, constraints, reasons)

        weighted_scores = [(time_score, 25.0)]
        if nutrition_score is not None:
            weighted_scores.append((nutrition_score, 45.0))
        if pantry_score is not None:
            weighted_scores.append((pantry_score, 30.0))

        total_score = sum(score * weight for score, weight in weighted_scores) / sum(
            weight for _, weight in weighted_scores
        )

        return RecipeRecommendationResponse(
            recipe=RecipeListItemResponse.model_validate(recipe),
            total_score=round(total_score, 1),
            score_breakdown=RecommendationScoreBreakdown(
                nutrition=round(nutrition_score, 1) if nutrition_score is not None else None,
                pantry=round(pantry_score, 1) if pantry_score is not None else None,
                time=round(time_score, 1),
            ),
            reasons=reasons,
        )

    @staticmethod
    def _time_score(recipe_minutes: int, maximum_minutes: int) -> float:
        return max(0.0, 100.0 - (recipe_minutes / maximum_minutes) * 40.0)

    def _nutrition_score(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        reasons: list[str],
    ) -> float | None:
        scores: list[float] = []
        targets = constraints.nutrition_targets
        target_pairs = [
            (float(recipe.nutrition.calories_kcal), targets.calories_kcal),
            (float(recipe.nutrition.protein_g), targets.protein_g),
            (float(recipe.nutrition.carbohydrate_g), targets.carbohydrate_g),
            (float(recipe.nutrition.fat_g), targets.fat_g),
        ]
        active_targets = [(actual, target) for actual, target in target_pairs if target is not None]
        scores.extend(self._target_closeness(actual, target) for actual, target in active_targets)
        if active_targets:
            reasons.append("Nutrition alignment was scored against your user-entered targets.")

        if "low-sodium" in constraints.health_preferences:
            sodium = float(recipe.nutrition.sodium_mg)
            scores.append(
                self._flexible_upper_score(
                    sodium,
                    FLEXIBLE_SODIUM_BENCHMARK_MG,
                    FLEXIBLE_SODIUM_UPPER_RANGE_MG,
                )
            )
            reasons.append(
                f"Low-sodium preference uses a flexible {FLEXIBLE_SODIUM_BENCHMARK_MG:.0f} mg "
                f"per-meal benchmark; this recipe has {sodium:.0f} mg."
            )

        if "low-sugar" in constraints.health_preferences:
            sugar = float(recipe.nutrition.sugar_g)
            scores.append(
                self._flexible_upper_score(
                    sugar,
                    FLEXIBLE_SUGAR_BENCHMARK_G,
                    FLEXIBLE_SUGAR_UPPER_RANGE_G,
                )
            )
            reasons.append(f"Low-sugar preference was scored using {sugar:g} g sugar per serving.")

        if "lower-calorie" in constraints.health_preferences:
            calories = float(recipe.nutrition.calories_kcal)
            scores.append(
                self._flexible_upper_score(
                    calories,
                    LOWER_CALORIE_BENCHMARK_KCAL,
                    LOWER_CALORIE_UPPER_RANGE_KCAL,
                )
            )
            reasons.append(f"Lower-calorie preference was scored using {calories:.0f} kcal per serving.")

        return sum(scores) / len(scores) if scores else None

    @staticmethod
    def _target_closeness(actual: float, target: float) -> float:
        if target == 0:
            return 100.0 if actual == 0 else 0.0
        return max(0.0, 100.0 - abs(actual - target) / target * 100.0)

    @staticmethod
    def _flexible_upper_score(actual: float, benchmark: float, upper_range: float) -> float:
        if actual <= benchmark:
            return 100.0
        return max(0.0, 100.0 - (actual - benchmark) / (upper_range - benchmark) * 100.0)

    @staticmethod
    def _pantry_score(
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        reasons: list[str],
    ) -> float | None:
        if not constraints.available_ingredients:
            return None

        available = {item.normalized_name: item for item in constraints.available_ingredients}
        household_scale = constraints.household_size / recipe.servings
        coverage = 0.0
        matched_count = 0

        for item in recipe.recipe_ingredients:
            pantry_item = available.get(item.ingredient.normalized_name)
            if pantry_item is None:
                continue
            matched_count += 1

            if pantry_item.quantity is None:
                coverage += 0.65
                continue

            required_quantity = float(item.quantity) * household_scale if item.quantity is not None else None
            if required_quantity and pantry_item.unit == item.unit:
                coverage += min(1.0, pantry_item.quantity / required_quantity)
            else:
                coverage += 0.65

        reasons.append(
            f"Matches {matched_count} of {len(recipe.recipe_ingredients)} recipe ingredients already available at home."
        )
        return coverage / len(recipe.recipe_ingredients) * 100.0 if recipe.recipe_ingredients else 0.0
