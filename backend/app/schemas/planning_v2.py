from datetime import date
from functools import cached_property
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.catalog_tags import CookingMethod, Equipment, EquipmentNeeds, MealRole, ProteinSource

MealType = Literal["breakfast", "lunch", "dinner", "snack"]
NutrientMetric = Literal[
    "calories_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "sodium_mg",
    "sugar_g",
]
# per_slot is the whole meal a slot holds: the sum of its dishes, each at its
# portion share (ADR-0036 section 4). per_dish is one dish's own serving.
NutritionScope = Literal["per_dish", "per_slot", "per_day", "horizon_average"]
# Released course labels a meal role may admit (ADR-0036 section 1).
DishCourse = Literal["main", "side", "salad", "soup", "breakfast", "dessert", "snack_appetizer", "baked_good"]
CheckStatus = Literal["passed", "failed", "indeterminate"]
PlanningStatus = Literal[
    "feasible",
    "candidate_rejected",
    "infeasible",
    "needs_clarification",
    "needs_data",
]


def _unset(value) -> bool:
    return value is None or value == []


# A newer optional key is left out of a dump while unset (None or []): stored constraints, packet digests and the
# protocol reports stay byte-identical for requests that never set it.
LEAN = {"exclude_if": _unset}


# Meal roles a lunch or dinner never takes (ADR-0070 section 3); breakfast dishes stay at breakfast.
NON_MEAL_ROLES = frozenset({"snack", "dessert", "sauce", "drink", "breakfast"})
CORE_MEAL_ROLES = frozenset({"protein_main", "one_bowl"})
STAPLE_ROLE = "staple"


class PlanningNutrients(BaseModel):
    calories_kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    sodium_mg: float = Field(ge=0)
    sugar_g: float = Field(ge=0)


class PlanningMealRole(BaseModel):
    """One dish position in a meal, filled by a recipe of one of its courses, or of one of its meal roles.

    A role of `courses` is the older form (ADR-0036, ADR-0046): protocol episodes and saved shapes keep it and
    plan exactly as before. A role of `meal_roles` (ADR-0070) admits recipes by their meal-role tag; its meal is
    then a real meal (filling core, staple, energy floor), and `min_people` plans it only when that many people
    eat the meal (the dinner that grows with the household).
    """

    model_config = ConfigDict(extra="forbid")
    role_id: str = Field(min_length=1, max_length=40)
    courses: list[DishCourse] = Field(default_factory=list)
    required: bool = True
    meal_roles: list[MealRole] | None = Field(default=None, min_length=1, **LEAN)
    min_people: int | None = Field(default=None, ge=1, le=12, **LEAN)

    @model_validator(mode="after")
    def one_way_to_admit(self) -> "PlanningMealRole":
        if bool(self.courses) == bool(self.meal_roles):
            raise ValueError("a meal role admits courses or meal roles: one of the two")
        if self.min_people is not None and not self.meal_roles:
            raise ValueError("only a meal-role role is planned by how many people are present")
        return self


def structured(roles) -> bool:
    """A meal of meal-role roles (ADR-0070); a meal's roles are all of one kind (`_composition_roles`)."""
    return bool(roles) and bool(getattr(roles[0], "meal_roles", None))


def core_role(roles) -> "PlanningMealRole | None":
    """A structured meal's filling core: its first role that takes a protein main or a one-bowl dish."""
    return next((role for role in roles or () if set(role.meal_roles or ()) & CORE_MEAL_ROLES), None)


def _composition_roles(roles: list[PlanningMealRole]) -> list[PlanningMealRole]:
    role_ids = [role.role_id for role in roles]
    if len(role_ids) != len(set(role_ids)):
        raise ValueError("meal role IDs must be unique within a composition")
    if not any(role.required for role in roles):
        raise ValueError("a meal composition needs at least one required role")
    kinds = {bool(role.meal_roles) for role in roles}
    if len(kinds) > 1:
        raise ValueError("a meal's roles admit courses or meal roles, not a mix of both")
    if kinds == {False} and len(roles) > 6:
        raise ValueError("a meal of course roles holds at most six dishes")
    return roles


def real_meal_roles(meal: str, roles: list[PlanningMealRole]) -> list[PlanningMealRole]:
    """A structured lunch or dinner is a real meal (ADR-0070 section 3): a required filling core, a staple role
    unless the core takes only one-bowl dishes, no role that takes a non-meal dish, a salad only as the vegetable
    dish and a soup only as the soup. Returns the roles; raises ValueError for a shape that breaks one."""
    if meal not in ("lunch", "dinner") or not structured(roles):
        return roles
    core = core_role(roles)
    if core is None or not core.required:
        raise ValueError(f"a {meal} needs a required protein main or one-bowl dish")
    if set(core.meal_roles or ()) != {"one_bowl"} and not any(role.role_id == STAPLE_ROLE for role in roles):
        raise ValueError(f"a {meal} with a protein main needs a staple role")
    for role in roles:
        admitted = set(role.meal_roles or ())
        base = role.role_id.split("-")[0]
        if admitted & NON_MEAL_ROLES:
            raise ValueError(f"a {meal} never takes {', '.join(sorted(admitted & NON_MEAL_ROLES))} dishes")
        if "salad" in admitted and base != "vegetable":
            raise ValueError("a salad fills only a vegetable role")
        if "soup" in admitted and base != "soup":
            raise ValueError("a soup fills only a soup role")
    return roles


# A household's dish roles for a meal, as a profile or a request states them.
MealComposition = Annotated[
    # Up to six dishes of courses (ADR-0046 raised ADR-0036's four); up to eight of meal roles: the full
    # default's dinner for seven and more is seven roles (ADR-0070).
    list[PlanningMealRole], Field(min_length=1, max_length=8), AfterValidator(_composition_roles)
]


class PlanningSlotMember(BaseModel):
    """A member home for this meal, with the limits that are this member's own (ADR-0071 section 1).

    The household-wide allergens, exclusions and diets of the problem apply to every dish on top of these; these
    decide which of those dishes are this member's food, how many servings each dish is cooked for, and whether
    this member is covered.
    """

    name: str = Field(min_length=1, max_length=80)
    servings: float = Field(gt=0, le=3)
    allergens: list[str] = Field(default_factory=list, max_length=20)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=200)
    dietary_requirements: list[str] = Field(default_factory=list, max_length=4)
    # The kcal this member needs from the meal: the HPB daily target times the meal's share (ADR-0070 section 3,
    # ADR-0071 section 3), measured against this member's portions of the dishes they can eat. None is no floor.
    min_energy_kcal: float | None = Field(default=None, ge=0)


class PlanningSlot(BaseModel):
    slot_id: str = Field(min_length=1, max_length=80)
    planned_date: date
    meal_type: MealType
    # The servings of the members home for this meal (layer 08): a decimal when portions are; a whole number
    # stays an int, so a slot dumps as before.
    servings: int | float = Field(gt=0, le=24)
    # The whole meal's time; for several dishes, the estimate of ADR-0036 section 3.
    max_time_minutes: int | None = Field(default=None, ge=5, le=360)
    # Only when the user says the limit applies to each dish.
    max_dish_time_minutes: int | None = Field(default=None, ge=5, le=360)
    required: bool = True
    locked_recipe_id: str | None = Field(default=None, max_length=120)
    # None is one dish per meal, as before. Role `main` takes the main share.
    composition: list[PlanningMealRole] | None = Field(default=None, min_length=1, max_length=8)
    # A composed meal's dishes that stay while one is added to it: role id -> recipe id.
    locked_roles: dict[str, str] | None = None
    # A structured lunch or dinner's energy floor per serving (ADR-0070 section 3): its dishes at their shares.
    min_energy_kcal: float | None = Field(default=None, ge=0, **LEAN)
    # The shopping trip that buys this meal's food (ADR-0072): 1 or 2 in a plan longer than a week, else None.
    trip: int | None = Field(default=None, ge=1, le=2, **LEAN)
    # Days since that trip, the trip's own day being 1 (layer 08 shelf life); None when the rule is off.
    days_after_shopping: int | None = Field(default=None, ge=1, le=14, **LEAN)
    # The members home for this meal and each one's own limits (ADR-0071 section 1); empty is the whole-table
    # rule this replaces: every dish is for everyone, cooked for `servings`, and nobody is checked separately.
    members: list[PlanningSlotMember] = Field(default_factory=list, max_length=12, **LEAN)

    @model_validator(mode="after")
    def validate_composition(self) -> "PlanningSlot":
        if self.composition is not None:
            _composition_roles(self.composition)
            if self.locked_recipe_id is not None:
                raise ValueError("lock a dish role, not a multi-dish slot, once role locks exist")
        if self.locked_roles and set(self.locked_roles) - {role.role_id for role in self.composition or []}:
            raise ValueError("a locked role must be a dish role of the slot")
        return self


class PlanningIngredientRequirement(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    # The recipe's own wording of the line; `app.planning.vegetable_led` reads it, nothing else does.
    original_text: str | None = None

    @model_validator(mode="after")
    def require_unit_for_known_quantity(self) -> "PlanningIngredientRequirement":
        if self.quantity is not None and self.unit is None:
            raise ValueError("unit is required when ingredient quantity is known")
        return self


class PlanningRecipeCandidate(BaseModel):
    # Layer 08 tags (PR-2), set only when the household's rules are on: a request without them keeps its packet.
    recipe_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    servings: int = Field(ge=1, le=24)
    # The meal types this recipe usually belongs to: a soft affinity the search
    # prefers, never a filter (ADR-0024 section 5).
    allowed_meal_types: list[MealType] = Field(min_length=1)
    total_time_minutes: int = Field(ge=0, le=720)
    dietary_tags: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    ingredients: list[PlanningIngredientRequirement] = Field(min_length=1)
    nutrients_per_serving: PlanningNutrients
    cuisine: str | None = Field(default=None, max_length=120)
    course: DishCourse | Literal["sauce_condiment", "drink"] | None = None
    # The split of total_time_minutes a multi-dish meal estimate needs; absent,
    # the whole time is treated as hands-on, the conservative reading.
    prep_minutes: int | None = Field(default=None, ge=0, le=720)
    cook_minutes: int | None = Field(default=None, ge=0, le=720)
    passive_minutes: int | None = Field(default=None, ge=0, le=720)
    meal_role: MealRole | None = Field(default=None, **LEAN)
    contains_staple: bool | None = Field(default=None, **LEAN)
    protein_sources: list[ProteinSource] | None = Field(default=None, **LEAN)
    cooking_methods: list[CookingMethod] | None = Field(default=None, **LEAN)
    # Every inner group is needed, one item of a group will do; None or [] needs nothing.
    equipment: EquipmentNeeds | None = Field(default=None, **LEAN)
    cuisine_group: str | None = Field(default=None, max_length=40, **LEAN)
    # A bought line is perishable: the dish is cooked within `FinalPlanningProblem.perishable_days` of its trip.
    perishable: bool | None = Field(default=None, **LEAN)

    @model_validator(mode="after")
    def validate_time_split(self) -> "PlanningRecipeCandidate":
        parts = (self.prep_minutes, self.cook_minutes, self.passive_minutes)
        if any(part is not None for part in parts):
            if any(part is None for part in parts):
                raise ValueError("prep, cook and passive minutes are given together or not at all")
            if sum(parts) != self.total_time_minutes:
                raise ValueError("prep, cook and passive minutes must sum to total_time_minutes")
        return self


class PlanningPantryItem(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    priority_use: bool = False

    @model_validator(mode="after")
    def require_unit_for_known_quantity(self) -> "PlanningPantryItem":
        if self.quantity is not None and self.unit is None:
            raise ValueError("unit is required when pantry quantity is known")
        return self


class PlanningProductOption(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    product_id: str = Field(min_length=1, max_length=160)
    package_quantity: float = Field(gt=0)
    package_unit: str = Field(min_length=1, max_length=40)
    price_sgd: float = Field(ge=0)
    available: bool = True


class PlanningNutritionBand(BaseModel):
    metric: NutrientMetric
    scope: NutritionScope
    lower: float | None = Field(default=None, ge=0)
    upper: float | None = Field(default=None, ge=0)
    hard: bool = True
    average_basis: Literal["represented_days", "selected_slots"] = "represented_days"
    purpose: Literal["constraint", "guard"] = "constraint"

    @model_validator(mode="after")
    def validate_bounds(self) -> "PlanningNutritionBand":
        if self.purpose == "guard" and (self.hard or self.scope != "per_slot"):
            raise ValueError("Nutrition guards must be soft per-slot bands")
        if self.average_basis == "selected_slots" and self.scope != "horizon_average":
            raise ValueError("Selected-slot averaging requires horizon_average scope")
        if self.lower is None and self.upper is None:
            raise ValueError("at least one nutrition bound is required")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("nutrition lower bound cannot exceed upper bound")
        return self


class PlanningPreferenceWeights(BaseModel):
    nutrition: float = Field(default=0.35, ge=0, le=1)
    variety: float = Field(default=0.25, ge=0, le=1)
    time: float = Field(default=0.15, ge=0, le=1)
    pantry: float = Field(default=0.15, ge=0, le=1)
    health: float = Field(default=0.10, ge=0, le=1)


class PlanningRecipeClassification(BaseModel):
    """Explicit recipe roles, supplied with the frozen packet; never inferred."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    core_ingredient_ids: list[str] = Field(min_length=1)
    primary_proteins: dict[str, str]
    source_reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_roles(self):
        cores = self.core_ingredient_ids
        if any(not item.strip() for item in cores) or len(cores) != len(set(cores)):
            raise ValueError("core ingredient IDs must be nonblank and unique")
        if not set(self.primary_proteins) <= set(cores):
            raise ValueError("primary protein ingredients must be core ingredients")
        if any(not group.strip() for group in self.primary_proteins.values()):
            raise ValueError("protein group IDs must be nonblank")
        return self


class PlanningDiversityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal["planning-diversity-v1"] = "planning-diversity-v1"
    classification_version: str = Field(min_length=1)
    classification_rule: str = Field(min_length=1)
    classifications: dict[str, PlanningRecipeClassification]
    max_slots_per_core_ingredient: int = Field(default=2, ge=1, le=84, strict=True)
    diversity_penalty: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    overlap_reward_weight: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)


class PlanningCompositionPolicy(BaseModel):
    """Portion shares and the meal-time estimate of ADR-0036 sections 2 and 3.

    Controlled parameters: recorded with the packet, tuned on developer data only.
    Index i holds the share for a meal of i + 1 dishes.
    """

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["planning-composition-v1"] = "planning-composition-v1"
    main_shares: list[float] = Field(default=[1.0, 0.75, 0.6, 0.5, 0.45, 0.4], min_length=1, max_length=6)
    other_shares: list[float | None] = Field(default=[None, 0.5, 0.4, 0.35, 0.3, 0.28], min_length=1, max_length=6)
    hands_on_cook_fraction: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    switch_minutes: int = Field(default=5, ge=0, le=60)
    round_to_minutes: int = Field(default=5, ge=1, le=15)
    # Structured meals' shares (data/planning/meal-structure-v1.json `portion_shares`), recorded with the packet.
    structured_shares: dict[str, list[float] | float] | None = Field(default=None, **LEAN)
    # A staple dish cooks unattended (the rice cooker): its cook time is waiting, not hands-on.
    staple_hands_off_cook: bool | None = Field(default=None, **LEAN)

    @model_validator(mode="after")
    def validate_shares(self) -> "PlanningCompositionPolicy":
        if len(self.main_shares) != len(self.other_shares):
            raise ValueError("main and other shares cover the same meal sizes")
        if self.main_shares[0] != 1.0 or self.other_shares[0] is not None:
            raise ValueError("a one-dish meal is the whole meal")
        for share in [*self.main_shares, *(s for s in self.other_shares[1:] if s is not None)]:
            if not 0 < share <= 1:
                raise ValueError("portion shares lie in (0, 1]")
        if any(share is None for share in self.other_shares[1:]):
            raise ValueError("every multi-dish size needs an other-dish share")
        return self


class PlanningRecipeCount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_id: str = Field(min_length=1, max_length=120)
    min_uses: int = Field(default=0, ge=0, le=84)
    max_uses: int | None = Field(default=None, ge=0, le=84)

    @model_validator(mode="after")
    def validate_range(self) -> "PlanningRecipeCount":
        if self.max_uses is not None and self.max_uses < self.min_uses:
            raise ValueError("a recipe's max_uses cannot be below its min_uses")
        return self


class PlanningIngredientMeals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ingredient_id: str = Field(min_length=1, max_length=160)
    min_meals: int = Field(ge=1, le=84)


class PlanningRepetitionRules(BaseModel):
    """What the household said about repeating (owner's choice, 2026-09-22).

    Only what the user said is hard. Saying nothing leaves repetition a soft
    penalty, which a role in `repeat_ok_roles` does not pay.
    """

    model_config = ConfigDict(extra="forbid")
    max_uses_per_recipe: int | None = Field(default=None, ge=1, le=84)  # "don't repeat" is 1
    recipe_counts: list[PlanningRecipeCount] = Field(default_factory=list)
    ingredient_meals: list[PlanningIngredientMeals] = Field(default_factory=list)
    repeat_ok_roles: list[str] = Field(default_factory=list)


class FinalPlanningProblem(BaseModel):
    problem_id: str = Field(min_length=1, max_length=120)
    slots: list[PlanningSlot] = Field(min_length=1, max_length=84)
    recipes: list[PlanningRecipeCandidate] = Field(min_length=1)
    pantry: list[PlanningPantryItem] = Field(default_factory=list)
    products: list[PlanningProductOption] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    # Allergens every candidate's `allergens` list was checked against. A requested
    # allergen outside it is unknown for every recipe and excludes them all
    # (ADR-0024 section 3); None means nothing was checked.
    allergen_vocabulary: list[str] | None = None
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_requirements: list[str] = Field(default_factory=list)
    health_preferences: list[Literal["low-sodium", "low-sugar", "lower-calorie"]] = Field(default_factory=list)
    nutrition_bands: list[PlanningNutritionBand] = Field(default_factory=list)
    purchase_budget_sgd: float | None = Field(default=None, gt=0)
    budget_is_hard: bool = True
    preference_weights: PlanningPreferenceWeights = Field(default_factory=PlanningPreferenceWeights)
    # None preserves legacy packets; it does not certify P3 diversity coverage.
    diversity_policy: PlanningDiversityPolicy | None = None
    composition_policy: PlanningCompositionPolicy = Field(default_factory=PlanningCompositionPolicy)
    repetition_rules: PlanningRepetitionRules | None = None
    # Equipment the household lacks (layer 08): a recipe whose equipment cannot be met is never planned.
    missing_equipment: list[Equipment] = Field(default_factory=list, **LEAN)
    # A perishable dish is planned within this many days of its shopping trip (ADR-0072); None is no rule.
    perishable_days: int | None = Field(default=None, ge=1, le=14, **LEAN)
    catalog_version: str
    product_snapshot_version: str
    policy_version: str

    @model_validator(mode="after")
    def validate_identity_and_locks(self) -> "FinalPlanningProblem":
        slot_ids = [slot.slot_id for slot in self.slots]
        recipe_ids = [recipe.recipe_id for recipe in self.recipes]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("planning slot IDs must be unique")
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("planning recipe IDs must be unique")
        known_recipes = set(recipe_ids)
        if self.diversity_policy is not None:
            for recipe_id, roles in self.diversity_policy.classifications.items():
                recipe = next((r for r in self.recipes if r.recipe_id == recipe_id), None)
                if recipe is None:
                    raise ValueError("classification refers to an unknown recipe")
                ingredients = {item.ingredient_id for item in recipe.ingredients}
                if not set(roles.core_ingredient_ids) <= ingredients:
                    raise ValueError("core ingredient is absent from recipe")
        unknown_locks = sorted(
            {
                slot.locked_recipe_id
                for slot in self.slots
                if slot.locked_recipe_id is not None and slot.locked_recipe_id not in known_recipes
            }
        )
        if unknown_locks:
            raise ValueError(f"locked recipes are missing from candidates: {unknown_locks}")
        return self

    @cached_property
    def uncounted_roles(self) -> frozenset[str]:
        """Roles whose repeats are by design (ADR-0070: rice by default at every meal), the staple of a structured
        meal: they pay no repeat cost and count towards no cap on uses."""
        return frozenset({STAPLE_ROLE}) if any(structured(slot.composition) for slot in self.slots) else frozenset()


class PlanningAssignment(BaseModel):
    slot_id: str
    recipe_id: str
    # The dish role in a composed slot; None in a one-dish slot.
    role_id: str | None = None


class PlanningShoppingSelection(BaseModel):
    ingredient_id: str
    required_quantity: float | None
    unit: str | None
    pantry_deduction: float = Field(ge=0)
    remaining_quantity: float | None
    selected_product_id: str | None
    packages: int = Field(ge=0)
    purchase_cost_sgd: float = Field(ge=0)
    surplus_quantity: float | None
    note: str | None = None
    # The shopping trip of a plan longer than a week (ADR-0072); None is the plan's only trip.
    trip: int | None = Field(default=None, ge=1, le=2, **LEAN)


class PlanningConstraintCheck(BaseModel):
    code: str
    status: CheckStatus
    hard: bool = True
    scope_id: str | None = None
    actual: float | str | None = None
    limit: float | str | None = None
    margin: float | None = None
    detail: str


class PlanningValidationReport(BaseModel):
    status: CheckStatus
    hard_failure_count: int = Field(ge=0)
    indeterminate_count: int = Field(ge=0)
    checks: list[PlanningConstraintCheck]
    purchase_total_sgd: float
    catalog_version: str
    product_snapshot_version: str
    policy_version: str


class PlanningTrace(BaseModel):
    algorithm: str
    algorithm_version: str
    deterministic: bool
    candidate_limit: int | None = None
    warnings: list[str] = Field(default_factory=list)
    diversity_policy: PlanningDiversityPolicy | None = None


class FinalPlanningSolution(BaseModel):
    problem_id: str
    status: PlanningStatus
    assignments: list[PlanningAssignment]
    shopping: list[PlanningShoppingSelection]
    validation: PlanningValidationReport
    trace: PlanningTrace
