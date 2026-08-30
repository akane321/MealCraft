from app.models.recipe import Recipe
from app.repositories.recipe import RecipeRepository
from app.schemas.recipe import (
    RecipeCollectionResponse,
    RecipeDetailResponse,
    RecipeIngredientResponse,
    RecipeListItemResponse,
    RecipeStepResponse,
)


class RecipeService:
    def __init__(self, repository: RecipeRepository) -> None:
        self.repository = repository

    def list_recipes(self, *, after_id: int | None, limit: int) -> RecipeCollectionResponse:
        recipes = self.repository.list_after(after_id=after_id, limit=limit)
        has_more = len(recipes) > limit
        visible_recipes = recipes[:limit]
        next_cursor = visible_recipes[-1].id if has_more and visible_recipes else None

        return RecipeCollectionResponse(
            items=[RecipeListItemResponse.model_validate(recipe) for recipe in visible_recipes],
            next_cursor=next_cursor,
        )

    def get_recipe(self, slug: str) -> RecipeDetailResponse | None:
        recipe = self.repository.get_by_slug(slug)
        if recipe is None:
            return None
        return self._to_detail(recipe)

    @staticmethod
    def _to_detail(recipe: Recipe) -> RecipeDetailResponse:
        return RecipeDetailResponse(
            **RecipeListItemResponse.model_validate(recipe).model_dump(),
            ingredients=[
                RecipeIngredientResponse(
                    name=item.ingredient.display_name,
                    normalized_name=item.ingredient.normalized_name,
                    quantity=float(item.quantity) if item.quantity is not None else None,
                    unit=item.unit,
                    preparation=item.preparation,
                    allergen=item.ingredient.allergen,
                )
                for item in recipe.recipe_ingredients
            ],
            steps=[
                RecipeStepResponse(step_number=step.step_number, instruction=step.instruction) for step in recipe.steps
            ],
        )
