from pydantic import BaseModel, ConfigDict, Field


class RecipeNutritionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calories_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    sodium_mg: float
    sugar_g: float


class RecipeListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    description: str
    cuisine: str
    meal_type: str
    servings: int
    total_time_minutes: int
    dietary_tags: list[str]
    nutrition: RecipeNutritionResponse


class RecipeCollectionResponse(BaseModel):
    items: list[RecipeListItemResponse]
    next_cursor: int | None = None


class RecipeIngredientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    normalized_name: str
    quantity: float | None
    unit: str | None
    preparation: str | None
    allergen: str | None


class RecipeStepResponse(BaseModel):
    step_number: int = Field(ge=1)
    instruction: str


class RecipeDetailResponse(RecipeListItemResponse):
    ingredients: list[RecipeIngredientResponse]
    steps: list[RecipeStepResponse]
