from bisect import bisect_left
from dataclasses import dataclass

from app.data import ingredient_hierarchy
from app.data.allergens import allergen_conflicts, conflict_reasons
from app.models.recipe import Recipe
from app.planning import alternatives
from app.planning.dietary_tags import expand_tags
from app.planning.member_coverage import MemberLimits, member_limits, title_mentions, unknown_safety_for
from app.planning.vegetable_led import vegetable_share, weighed
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
# The planner searches at most this many recommendations. They are the best
# scored within budget across the whole catalog, not the first rows by id.
CANDIDATE_LIMIT = 500


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
        # Expanded once per call, not per recipe: "no pork" also removes bacon.
        excluded_ingredients = ingredient_hierarchy.expand_exclusions(constraints.excluded_ingredients)
        # The shared-dish model (ADR-0071 section 1): each member's own exclusions and diet, expanded once.
        members = member_limits(getattr(constraints, "household", None))

        eligible = []
        for recipe in recipes:
            exclusion_reasons = self._exclusion_reasons(recipe, constraints, excluded_ingredients, members)
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
            eligible.append(recipe)

        # A member's muscle-gain goal (layer 08): a dish's protein per serving as a percentile of the eligible
        # dishes joins the nutrition score, so protein-rich dishes rank higher with no invented target.
        household = getattr(constraints, "household", None)
        proteins = sorted(float(recipe.nutrition.protein_g) for recipe in eligible)
        for recipe in eligible:
            protein_rank = None
            if household is not None and household.protein_priority:
                protein = float(recipe.nutrition.protein_g)
                protein_rank = 100.0 * bisect_left(proteins, protein) / max(1, len(proteins) - 1)
            response = self._score_recipe(recipe, constraints, protein_rank)
            scored.append(ScoredRecipe(recipe=recipe, response=response))

        scored.sort(key=lambda item: (-item.response.total_score, item.recipe.id))
        excluded.sort(key=lambda item: item.id)
        return [item.response for item in scored], excluded

    def _exclusion_reasons(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        excluded_ingredients: list[str],
        members: list[MemberLimits] | None = None,
    ) -> list[str]:
        """Why this household cannot have the recipe at all.

        The household's own allergens, exclusions, diets, time and sodium limits reject it as before. With
        members, their exclusions and diets reject it only when no member can eat it: a dish is served when at
        least one present member can (ADR-0071 section 1). Allergens are the whole household's by default; an
        allergen only one member avoids is that member's own and is checked here per member (section 2).
        """
        reasons: list[str] = []
        # "Never again" is the whole household's, whoever pressed it (ADR-0087).
        if recipe.slug in constraints.never_again_recipes:
            reasons.append("You asked not to plan this dish again.")
        # An "A or B" line counts as the option this household can eat, if there is one.
        cooked = alternatives.lines(recipe, constraints)
        ingredient_names = {item.ingredient.normalized_name for item in cooked}
        recipe_allergens = {allergen for item in cooked for allergen in item.ingredient.allergens}
        reasons.extend(conflict_reasons(*allergen_conflicts(constraints.allergens, recipe_allergens)))
        if constraints.allergens and "allergens" in (recipe.unknown_safety or []):
            reasons.append("allergen_status_unknown")
        if constraints.dietary_preferences and "diet" in (recipe.unknown_safety or []):
            reasons.append("dietary_status_unknown")
        if constraints.requires_halal and recipe.halal_status != "halal":
            reasons.append("halal_requirement")

        excluded_matches = sorted(ingredient_names.intersection(excluded_ingredients))
        if excluded_matches:
            reasons.append(
                f"Contains excluded ingredient: {', '.join(self._named_by_household(excluded_matches, constraints))}."
            )

        # A safety net for incomplete data: a release recipe can lose its main line
        # ("Korean Pork Chops" with no pork listed), so its name is checked as well.
        named = title_mentions(recipe.title, [*constraints.excluded_ingredients, *constraints.allergens])
        if named and not excluded_matches:
            reasons.append(f"Its name mentions {', '.join(named)}, which this household avoids.")

        if recipe.total_time_minutes > constraints.max_cooking_time_minutes:
            reasons.append(
                f"Requires {recipe.total_time_minutes} minutes, above the "
                f"{constraints.max_cooking_time_minutes}-minute limit."
            )

        recipe_tags = set(recipe.dietary_tags)
        for preference in constraints.dietary_preferences:
            if not self._satisfies_dietary_preference(preference, recipe_tags):
                reasons.append(f"Does not satisfy the {preference} requirement.")

        if members:
            blocked = [(member, why) for member in members if (why := self._member_reasons(recipe, cooked, member))]
            if len(blocked) == len(members):
                told = "; ".join(f"{member.name}: {' '.join(why)}" for member, why in blocked)
                reasons.append(f"No member of this household can eat it. {told}")

        sodium_limit = constraints.max_sodium_mg_per_meal
        if sodium_limit is not None and float(recipe.nutrition.sodium_mg) > sodium_limit:
            reasons.append(
                f"Contains {float(recipe.nutrition.sodium_mg):.0f} mg sodium per serving, "
                f"above the user-entered {sodium_limit:.0f} mg limit."
            )

        return reasons

    def _member_reasons(self, recipe: Recipe, cooked: list, member: MemberLimits) -> list[str]:
        """Why this one member cannot eat the recipe: their own allergens, exclusions and diet."""
        reasons: list[str] = []
        reasons.extend(unknown_safety_for(member, recipe))
        recipe_allergens = {allergen for item in cooked for allergen in item.ingredient.allergens}
        present, unverifiable = allergen_conflicts(sorted(member.allergens), recipe_allergens)
        reasons.extend(conflict_reasons(present, unverifiable))
        matches = sorted({item.ingredient.normalized_name for item in cooked} & member.excluded_ingredients)
        if matches:
            reasons.append(f"Contains excluded ingredient: {', '.join(matches)}.")
        named = title_mentions(recipe.title, [*member.stated, *sorted(member.allergens)])
        if named and not matches:
            reasons.append(f"Its name mentions {', '.join(named)}.")
        recipe_tags = set(recipe.dietary_tags)
        reasons.extend(
            f"Does not satisfy the {preference} requirement."
            for preference in member.dietary_requirements
            if not self._satisfies_dietary_preference(preference, recipe_tags)
        )
        return reasons

    @staticmethod
    def _satisfies_dietary_preference(preference: str, recipe_tags: set[str]) -> bool:
        """Entailments come from the shared table, not from this function.

        These two rules used to live here as literals, which is how this path
        ended up more permissive than the v2 planner: both encoded the same idea
        and only one of them was updated. One definition, one place.
        """
        return preference in expand_tags(recipe_tags)

    @staticmethod
    def _named_by_household(matches: list[str], constraints: RecipeRecommendationRequest) -> list[str]:
        """Say which of the household's own words removed each match: `bacon (excluded: pork)`.

        A match the household named itself stays as it was. Without this a household
        that said "no pork" is told the recipe "contains excluded ingredient: bacon".
        """
        named = set(constraints.excluded_ingredients)
        labelled = []
        for match in matches:
            because = sorted(ingredient_hierarchy.runtime().ancestors(match) & named) if match not in named else []
            labelled.append(f"{match} (excluded: {', '.join(because)})" if because else match)
        return labelled

    def _score_recipe(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        protein_rank: float | None = None,
    ) -> RecipeRecommendationResponse:
        reasons = [
            f"Fits the {constraints.max_cooking_time_minutes}-minute limit ({recipe.total_time_minutes} minutes)."
        ]
        time_score = self._time_score(recipe.total_time_minutes, constraints.max_cooking_time_minutes)
        nutrition_score = self._nutrition_score(recipe, constraints, reasons, protein_rank)
        pantry_score = self._pantry_score(recipe, constraints, reasons)
        preference_score = self._preference_score(recipe, constraints, reasons)

        weighted_scores = [(time_score, 25.0)]
        if nutrition_score is not None:
            weighted_scores.append((nutrition_score, 45.0))
        if pantry_score is not None:
            weighted_scores.append((pantry_score, 30.0))
        if preference_score is not None:
            weighted_scores.append((preference_score, 20.0))

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

    def _preference_score(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        reasons: list[str],
    ) -> float | None:
        preferences = constraints.planning_preferences
        scores: list[float] = []
        if preferences.more_vegetables:
            share = vegetable_share(
                weighed(
                    (
                        line.ingredient.normalized_name,
                        line.quantity,
                        line.unit,
                        line.original_text,
                    )
                    for line in alternatives.lines(recipe, constraints)
                )
            )
            if share is not None:
                scores.append(share * 100)
                reasons.append(f"Vegetables make up {share:.0%} of the weighed ingredients.")
        if preferences.lighter:
            sodium = float(recipe.nutrition.sodium_mg)
            fat = float(recipe.nutrition.fat_g)
            scores.extend(
                [
                    self._flexible_upper_score(sodium, 500.0, 1000.0),
                    self._flexible_upper_score(fat, 15.0, 30.0),
                ]
            )
            reasons.append("Lighter meals are ranked using per-serving sodium and fat from the recipe catalog.")
        flavor_boosts = [item.flavor for item in preferences.flavor_boosts if not item.weekdays and not item.meal_types]
        if flavor_boosts and recipe.flavor_tags is not None:
            matched = sum(flavor in recipe.flavor_tags for flavor in set(flavor_boosts))
            scores.append(100.0 * matched / len(set(flavor_boosts)))
            reasons.append("Flavor preferences are ranked against the recipe's catalog flavor tags.")
        return sum(scores) / len(scores) if scores else None

    @staticmethod
    def _time_score(recipe_minutes: int, maximum_minutes: int) -> float:
        return max(0.0, 100.0 - (recipe_minutes / maximum_minutes) * 40.0)

    def _nutrition_score(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
        reasons: list[str],
        protein_rank: float | None = None,
    ) -> float | None:
        scores: list[float] = []
        if protein_rank is not None:
            scores.append(protein_rank)
            reasons.append("Protein-rich dishes rank higher for a muscle-gain goal.")
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

        cooked = alternatives.lines(recipe, constraints)
        for item in cooked:
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

        reasons.append(f"Matches {matched_count} of {len(cooked)} recipe ingredients already available at home.")
        return coverage / len(cooked) * 100.0 if cooked else 0.0
