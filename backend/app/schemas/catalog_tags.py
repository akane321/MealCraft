"""Recipe, ingredient, retailer and feedback types of the Sprint 2 schema foundation.

They are defined here and not yet wired: no request or response model uses them, so the API is unchanged
until a feature PR wires one in. The meanings, NULL rules and storage are in
docs/design/sprint2-schema-foundation.md. Where a column has a CHECK constraint, its value list in app/models
and in migration 20261018_0030 is the same as the Literal here (tests/test_sprint2_foundation_types.py).
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# What a dish can be in a meal (recipes.meal_role). One-bowl dishes fill the main and the staple at once;
# snack, dessert, sauce and drink never fill a lunch or dinner.
MealRole = Literal[
    "protein_main",
    "vegetable",
    "soup",
    "staple",
    "one_bowl",
    "breakfast",
    "salad",
    "snack",
    "dessert",
    "sauce",
    "drink",
]
# Main protein sources (recipes.protein_sources). Chicken and duck are separate sources.
ProteinSource = Literal["chicken", "duck", "pork", "beef", "lamb", "fish", "shellfish", "soy", "egg", "legume"]
CookingMethod = Literal["deep_fry", "stir_fry", "pan_fry", "steam", "boil", "braise", "bake", "grill", "raw"]
FlavorTag = Literal["fragrant", "spicy", "light", "rich"]
Equipment = Literal["oven", "air_fryer", "steamer", "microwave", "blender"]
# recipes.equipment: every inner group is needed, and any one item of a group will do,
# so [["oven", "air_fryer"], ["blender"]] is "an oven or an air fryer, and a blender".
EquipmentNeeds = list[Annotated[list[Equipment], Field(min_length=1)]]
# A recipe's halal status is about its ingredients only. needs_certification: halal only when its meat is
# bought as a certified product, which the planner checks on the product.
HalalStatus = Literal["halal", "needs_certification", "not_halal", "uncertain"]
IngredientHalalStatus = Literal["halal", "not_halal", "uncertain"]
# recipes.unknown_safety: the safety facts not yet confirmed. A household with that kind of limit never
# gets the recipe; an unknown is never read as safe.
UnknownSafety = Literal["allergens", "halal", "diet"]
FeedbackKind = Literal["like", "dislike", "never_again"]
FeedbackSource = Literal["button", "chat"]

# The recipe columns an AI or rule estimate may fill (recipes.estimated). Servings and time keep their own
# servings_basis and time_basis; safety labels are never estimated.
EstimatedRecipeField = Literal[
    "meal_role", "contains_staple", "protein_sources", "cooking_methods", "flavor_tags", "equipment"
]


class FieldEstimate(BaseModel):
    """How one recipe field was estimated, and in which batch."""

    model_config = ConfigDict(extra="forbid")
    method: Literal["rule", "llm"]
    batch: str = Field(min_length=1, max_length=80)
    # True once a person checked this recipe's value in the batch sample.
    reviewed: bool = False


# recipes.estimated: field name -> how it was filled. A field not listed is as released.
RecipeEstimates = dict[EstimatedRecipeField, FieldEstimate]


class IngredientLineProvenance(BaseModel):
    """Where one recipe ingredient line came from (recipe_ingredients.provenance)."""

    model_config = ConfigDict(extra="forbid")
    quantity_estimated: bool = False
    # The line was added from the steps, which use it while the ingredient list leaves it out.
    from_steps: bool = False
    # How the line's text was matched to a canonical ingredient; None when not recorded.
    match: Literal["exact", "alias", "embedding", "parent"] | None = None
    reviewed: bool = False


class IngredientProvenance(BaseModel):
    """Where a non-release ingredient row came from (ingredients.provenance)."""

    model_config = ConfigDict(extra="forbid")
    origin: Literal["extension_table", "external_intake"]
    nutrition_source: str | None = Field(default=None, max_length=200)
    price_source: str | None = Field(default=None, max_length=200)


# Every retailer an adapter may name. A new retailer is one more entry here: the stored value is this slug
# and no CHECK constraint lists it.
RETAILERS: tuple[str, ...] = (
    "fairprice",
    "sheng_siong",
    "cold_storage",
    "giant",
    "redmart",
    "shopee",
    "lazada",
)


def _registered_retailer(value: str) -> str:
    if value not in RETAILERS:
        raise ValueError(f"unknown retailer {value!r}; register it in RETAILERS")
    return value


Retailer = Annotated[
    str, Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$"), AfterValidator(_registered_retailer)
]


class RetailerChoice(BaseModel):
    """The product one retailer offers for one ingredient, or that it offers none."""

    model_config = ConfigDict(extra="forbid")
    ingredient: str = Field(min_length=1, max_length=160)
    retailer: Retailer
    # None: the retailer has no product on sale for this ingredient.
    product_external_id: str | None = Field(default=None, min_length=1)
