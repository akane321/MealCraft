"""Deterministic admission review for structured external recipe candidates.

This module does not fetch pages or persist records. It checks the typed extraction before
any caller can pass it to a household planner; page text remains untrusted input.
"""

import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.data.external_ingredient_mapping import ReviewedIngredientMapper
from app.data.external_source_policies import (
    POLICY_VERSION,
    AcquisitionMethod,
    resolve_external_source_policy,
)
from app.data.recipe_tags import Dish, Line, rule_tags
from app.data.release_v2 import RELEASE_VERSION
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.schemas.planning_v2 import DishCourse, MealType


class ExternalIngredientLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=200)
    grams: float | None = Field(default=None, gt=0)
    canonical_id: str | None = Field(default=None, min_length=1, max_length=160)
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    allergens: list[str] | None = None  # None means unknown; [] means checked and none found.
    halal_status: Literal["halal", "needs_certification", "not_halal", "uncertain"] | None = None

    @model_validator(mode="after")
    def mapping_has_confidence(self) -> "ExternalIngredientLine":
        if self.canonical_id is not None and self.match_confidence is None:
            raise ValueError("mapped ingredient lines require a mapping confidence")
        if self.canonical_id is None and self.match_confidence is not None:
            raise ValueError("unmapped ingredient lines cannot carry a mapping confidence")
        return self


class ExternalRecipeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    source_url: HttpUrl
    source_tier: Literal[1, 2]
    license: str | None = Field(default=None, min_length=1, max_length=200)
    retrieved_at: datetime
    steps_basis: Literal["source", "rewritten"]
    servings: int | None = Field(default=None, ge=1, le=100)
    servings_basis: Literal["stated", "estimated"] | None = None
    prep_time_minutes: int | None = Field(default=None, ge=0, le=10080)
    cook_time_minutes: int | None = Field(default=None, ge=0, le=10080)
    time_basis: Literal["stated", "estimated"] | None = None
    passive_time_minutes: int | None = Field(default=None, ge=0, le=10080)
    course: str | None = None
    cuisine: str | None = None
    meal_types: list[str] | None = None
    difficulty: str | None = None
    nutrition_per_serving: dict[str, float] | None = None
    ingredients: list[ExternalIngredientLine] = Field(min_length=1)
    steps: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("steps", mode="before")
    @classmethod
    def sanitize_steps(cls, value):
        if not isinstance(value, list):
            return value
        cleaned = []
        unsafe = re.compile(
            r"(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
            r"system\s+prompt|developer\s+message|reveal\s+(?:the\s+)?prompt|"
            r"忽略.{0,12}(?:指令|提示)|系统提示|开发者消息)",
            re.IGNORECASE,
        )
        url = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
        for item in value:
            if not isinstance(item, str):
                cleaned.append(item)
                continue
            if unsafe.search(item):
                continue
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", item)
            text = url.sub("", text).strip()
            if text:
                if len(text) > 500:
                    raise ValueError("a recipe step exceeds the length limit")
                cleaned.append(text)
        if sum(len(item) for item in cleaned if isinstance(item, str)) > 6000:
            raise ValueError("recipe steps exceed the total length limit")
        return cleaned

    @field_validator("nutrition_per_serving")
    @classmethod
    def nonnegative_nutrients(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and any(amount < 0 for amount in value.values()):
            raise ValueError("nutrition values cannot be negative")
        return value

    @model_validator(mode="after")
    def source_terms_and_times(self) -> "ExternalRecipeDraft":
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        if self.source_tier == 2 and self.steps_basis != "rewritten":
            raise ValueError("tier 2 source steps must be rewritten")
        if self.servings is not None and self.servings_basis is None:
            raise ValueError("servings_basis is required when servings are present")
        if (self.prep_time_minutes or 0) + (self.cook_time_minutes or 0) == 0:
            if self.prep_time_minutes is not None and self.cook_time_minutes is not None:
                raise ValueError("prep and cook time cannot both be zero")
        return self


class ExternalRecipeReview(BaseModel):
    mapping_coverage: float
    quality_score: float
    unknown_safety: list[Literal["allergens", "halal", "dietary_tags"]]
    safety_conflicts: list[str]
    missing_fields: list[str]
    eligible_for_household: bool
    requires_halal: bool = False
    requires_allergen_check: bool = False
    requires_diet_check: bool = False


NUTRIENT_FIELDS = {
    "calories_kcal": "energy_kcal",
    "protein_g": "protein_g",
    "carbohydrate_g": "carbohydrate_g",
    "fat_g": "fat_g",
    "sodium_mg": "sodium_mg",
    "sugar_g": "sugar_g",
}


@lru_cache(maxsize=1)
def _released_nutrition_per_100g() -> dict[str, dict[str, float]]:
    """Load the released canonical ingredient nutrition used for deterministic intake totals."""
    path = repository_root() / f"data-engineering/data/release/{RELEASE_VERSION}/ingredients.jsonl"
    values: dict[str, dict[str, float]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        ingredient = json.loads(raw)
        for form_id, form in ingredient.get("forms", {}).items():
            nutrition = form.get("nutrition_per_100g") or {}
            if not all(source in nutrition for source in NUTRIENT_FIELDS.values()):
                continue
            normalized_id = form_id.removeprefix("ING_").split("#", 1)[0].casefold()
            candidate = {target: float(nutrition[source]) for target, source in NUTRIENT_FIELDS.items()}
            # Prefer the unqualified canonical form over a form-specific override.
            if normalized_id not in values or "#" not in form_id:
                values[normalized_id] = candidate
    return values


def compute_nutrition_per_serving(draft: ExternalRecipeDraft) -> dict[str, float] | None:
    """Compute recipe nutrition from weighed canonical lines; never trust extracted macro totals."""
    if draft.servings is None or not draft.ingredients:
        return None
    ingredient_nutrients = _released_nutrition_per_100g()
    totals = dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    for line in draft.ingredients:
        if line.canonical_id is None or line.grams is None:
            return None
        nutrients = ingredient_nutrients.get(line.canonical_id.casefold())
        if nutrients is None:
            return None
        for field in totals:
            totals[field] += nutrients[field] * line.grams / 100
    return {field: round(value / draft.servings, 2) for field, value in totals.items()}


def map_ingredient_lines(
    draft: ExternalRecipeDraft,
    *,
    mapper: ReviewedIngredientMapper,
    catalog_ingredients: dict[str, object],
) -> ExternalRecipeDraft:
    """Replace untrusted extracted identities and safety claims using reviewed aliases and catalog facts."""
    mapped_lines: list[ExternalIngredientLine] = []
    for line in draft.ingredients:
        match = mapper.resolve(line.source_name)
        ingredient = catalog_ingredients.get(match.canonical_id or "") if match.status == "matched" else None
        if ingredient is None:
            mapped_lines.append(
                line.model_copy(
                    update={"canonical_id": None, "match_confidence": None, "allergens": None, "halal_status": None}
                )
            )
            continue
        mapped_lines.append(
            line.model_copy(
                update={
                    "canonical_id": ingredient.normalized_name,
                    "match_confidence": match.confidence,
                    "allergens": ingredient.allergens,
                    "halal_status": ingredient.halal_status,
                }
            )
        )
    return ExternalRecipeDraft.model_validate(
        {**draft.model_dump(mode="python"), "ingredients": [line.model_dump() for line in mapped_lines]}
    )


def review_external_recipe(
    draft: ExternalRecipeDraft,
    *,
    household_allergens: list[str] | None = None,
    excluded_ingredients: list[str] | None = None,
    requires_halal: bool = False,
    household_dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free", "dairy-free"]] | None = None,
    minimum_mapping_coverage: float = 0.9,
    minimum_quality_score: float = 0.8,
) -> ExternalRecipeReview:
    """Score extraction quality and fail closed for household safety constraints."""
    if not 0 <= minimum_mapping_coverage <= 1 or not 0 <= minimum_quality_score <= 1:
        raise ValueError("review thresholds must be between 0 and 1")

    total_grams = sum(line.grams or 0 for line in draft.ingredients)
    mapped_grams = sum(line.grams or 0 for line in draft.ingredients if line.canonical_id is not None)
    has_unknown_gram_weight = any(line.grams is None for line in draft.ingredients)
    coverage = mapped_grams / total_grams if total_grams and not has_unknown_gram_weight else 0.0
    quality = (
        sum((line.grams or 0) * (line.match_confidence or 0) for line in draft.ingredients) / total_grams
        if total_grams and not has_unknown_gram_weight
        else 0.0
    )

    required = {
        "title": draft.title,
        "servings": draft.servings,
        "prep_time_minutes": draft.prep_time_minutes,
        "cook_time_minutes": draft.cook_time_minutes,
        "time_basis": draft.time_basis,
        "course": draft.course,
        "cuisine": draft.cuisine,
        "meal_types": draft.meal_types,
        "difficulty": draft.difficulty,
        "nutrition_per_serving": draft.nutrition_per_serving,
        "steps": draft.steps,
    }
    missing = [name for name, value in required.items() if value is None or value == "" or value == []]
    if draft.course not in get_args(DishCourse):
        missing.append("supported_course")
    if not draft.meal_types or any(item not in get_args(MealType) for item in draft.meal_types):
        missing.append("supported_meal_types")
    if draft.difficulty not in {"easy", "medium", "hard"}:
        missing.append("supported_difficulty")
    tags = _planning_tags(draft)
    missing.extend(name for name in ("meal_role", "contains_staple", "protein_sources") if tags.values[name] is None)
    if tags.incomplete_reason:
        missing.append("incomplete_ingredient_evidence")
    if draft.steps_basis != "rewritten":
        missing.append("rewritten_steps")
    if draft.license is None:
        missing.append("license")
    required_nutrients = {"calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g"}
    if draft.nutrition_per_serving is not None and not required_nutrients <= draft.nutrition_per_serving.keys():
        missing.append("nutrition_per_serving")
    if draft.servings is not None and draft.servings_basis is None:
        missing.append("servings_basis")
    if any(line.grams is None for line in draft.ingredients):
        missing.append("ingredient_grams")
    if any(line.canonical_id is None for line in draft.ingredients):
        missing.append("unmapped_ingredient")
    if coverage < minimum_mapping_coverage:
        missing.append("ingredient_mapping_coverage")
    if quality < minimum_quality_score:
        missing.append("quality_score")

    wanted_allergens = {item.casefold() for item in household_allergens or []}
    unverifiable_requested = wanted_allergens - {item.casefold() for item in checked_allergens()}
    excluded = {item.casefold() for item in excluded_ingredients or []}
    known_allergens = {allergen.casefold() for line in draft.ingredients for allergen in (line.allergens or [])}
    unknown_allergens = any(line.allergens is None for line in draft.ingredients)
    unknown_halal = any(line.halal_status in {None, "uncertain", "needs_certification"} for line in draft.ingredients)
    unknown_mapping = any(line.canonical_id is None for line in draft.ingredients)
    unknown_dietary_tags = True  # External diet labels are not yet reviewed against our tag definitions.
    conflicts: set[str] = set()
    conflicts.update(f"allergen:unverifiable:{item}" for item in unverifiable_requested)
    if excluded and unknown_mapping:
        conflicts.add("exclusion:cannot_check_unmapped_ingredient")
    if wanted_allergens.intersection(known_allergens):
        conflicts.update(wanted_allergens.intersection(known_allergens))
    if excluded.intersection(
        line.canonical_id.casefold() for line in draft.ingredients if line.canonical_id is not None
    ):
        conflicts.update(
            f"excluded:{name}"
            for name in excluded.intersection(
                line.canonical_id.casefold() for line in draft.ingredients if line.canonical_id is not None
            )
        )
    if requires_halal and any(line.halal_status == "not_halal" for line in draft.ingredients):
        conflicts.add("halal:not_halal")

    unknown_safety: list[Literal["allergens", "halal", "dietary_tags"]] = []
    if unknown_allergens:
        unknown_safety.append("allergens")
    if unknown_halal:
        unknown_safety.append("halal")
    if unknown_dietary_tags:
        unknown_safety.append("dietary_tags")
        if household_dietary_preferences:
            missing.append("verified_dietary_tags")
    safety_blocks_household = (
        bool(wanted_allergens and unknown_allergens)
        or (requires_halal and unknown_halal)
        or (bool(household_dietary_preferences) and unknown_dietary_tags)
    )
    eligible = not missing and not conflicts and not safety_blocks_household
    return ExternalRecipeReview(
        mapping_coverage=round(coverage, 4),
        quality_score=round(quality, 4),
        unknown_safety=unknown_safety,
        safety_conflicts=sorted(conflicts),
        missing_fields=missing,
        eligible_for_household=eligible,
        requires_halal=requires_halal,
        requires_allergen_check=bool(household_allergens),
        requires_diet_check=bool(household_dietary_preferences),
    )


def normalize_recipe_title(title: str) -> str:
    """Normalize punctuation and accents for deterministic duplicate checks."""
    folded = unicodedata.normalize("NFKD", title).casefold()
    letters = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W_]+", letters, flags=re.UNICODE))


def _planning_tags(draft: ExternalRecipeDraft):
    nutrients = draft.nutrition_per_serving or {}
    return rule_tags(
        Dish(
            key="external-intake",
            title=draft.title or "",
            course=draft.course or "",
            cuisine=draft.cuisine or "",
            servings=draft.servings or 1,
            kcal=nutrients.get("calories_kcal"),
            fat_g=nutrients.get("fat_g"),
            sugar_g=nutrients.get("sugar_g"),
            carbohydrate_g=nutrients.get("carbohydrate_g"),
            lines=[
                Line(name=line.canonical_id or "", grams=line.grams, text=line.source_name)
                for line in draft.ingredients
            ],
            steps="\n".join(draft.steps),
        )
    )


def find_duplicate_recipe(draft: ExternalRecipeDraft, existing_recipes: Iterable[object]) -> object | None:
    """Return an existing recipe only for an exact normalized-title and canonical-set match."""
    if draft.title is None or any(line.canonical_id is None for line in draft.ingredients):
        return None
    candidate_ingredients = {line.canonical_id for line in draft.ingredients}
    if not candidate_ingredients:
        return None
    candidate_title = normalize_recipe_title(draft.title)
    for recipe in existing_recipes:
        if normalize_recipe_title(recipe.title) != candidate_title:
            continue
        existing_ingredients = {line.ingredient.normalized_name for line in recipe.recipe_ingredients}
        if existing_ingredients == candidate_ingredients:
            return recipe
    return None


def persist_admitted_recipe(
    session: Session,
    draft: ExternalRecipeDraft,
    review: ExternalRecipeReview,
    *,
    household_id: int,
    acquisition_method: AcquisitionMethod = "user_supplied",
) -> tuple[Recipe, bool]:
    """Persist a fully mapped, reviewed recipe privately; return (recipe, created)."""
    if household_id <= 0:
        raise ValueError("A valid household is required for external recipe intake")
    if not review.eligible_for_household or review.missing_fields or review.safety_conflicts:
        raise ValueError("The candidate did not pass the household admission review")
    if "allergens" in review.unknown_safety and review.requires_allergen_check:
        raise ValueError("Unknown allergen status cannot be stored for a household with allergen constraints")
    if "dietary_tags" in review.unknown_safety and review.requires_diet_check:
        raise ValueError("Unverified dietary tags cannot be stored for a household with dietary constraints")
    if "halal" in review.unknown_safety and review.requires_halal:
        raise ValueError("Unknown ingredient safety cannot be stored as a plannable recipe")
    if any(line.canonical_id is None or line.grams is None for line in draft.ingredients):
        raise ValueError("Every ingredient must be mapped and weighed before persistence")
    if (
        draft.title is None
        or draft.servings is None
        or draft.prep_time_minutes is None
        or draft.cook_time_minutes is None
    ):
        raise ValueError("The candidate is missing required recipe fields")
    if draft.course not in get_args(DishCourse):
        raise ValueError("The candidate course is outside the supported meal-planning vocabulary")
    if not draft.meal_types or any(item not in get_args(MealType) for item in draft.meal_types):
        raise ValueError("The candidate meal types are outside the supported vocabulary")
    if draft.difficulty not in {"easy", "medium", "hard"}:
        raise ValueError("The candidate difficulty is outside the supported vocabulary")
    if draft.nutrition_per_serving is None or not draft.steps:
        raise ValueError("The candidate is missing nutrition or steps")
    if draft.steps_basis != "rewritten":
        raise ValueError("Unverified external source steps must be rewritten before persistence")
    if review.requires_halal and any(line.halal_status != "halal" for line in draft.ingredients):
        raise ValueError("Every ingredient must have verified halal status")
    tags = _planning_tags(draft)
    if tags.incomplete_reason or any(
        tags.values[name] is None for name in ("meal_role", "contains_staple", "protein_sources")
    ):
        raise ValueError("The candidate has no verified planning role or protein evidence")

    ingredient_names = {line.canonical_id for line in draft.ingredients}
    ingredients = {
        row.normalized_name: row
        for row in session.scalars(select(Ingredient).where(Ingredient.normalized_name.in_(ingredient_names)))
    }
    if ingredient_names != set(ingredients):
        raise ValueError("A mapped catalog ingredient is no longer available")

    policy = resolve_external_source_policy(str(draft.source_url), acquisition_method=acquisition_method)
    source = {
        "dataset": "web-intake",
        "source_type": "web",
        "tier": policy.tier,
        "url": str(draft.source_url),
        "retrieved_at": draft.retrieved_at.isoformat(),
        "license": policy.license_note,
        "license_status": policy.license_status,
        "source_policy_id": policy.policy_id,
        "source_policy_version": POLICY_VERSION,
        "steps_basis": draft.steps_basis,
    }
    if policy.policy_reference:
        source["source_policy_reference"] = policy.policy_reference
    visibility = or_(Recipe.owner_household_id.is_(None), Recipe.owner_household_id == household_id)
    existing = (
        session.scalars(
            select(Recipe)
            .where(visibility)
            .options(selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient))
        )
        .unique()
        .all()
    )
    duplicate = find_duplicate_recipe(
        draft, [recipe for recipe in existing if recipe.owner_household_id == household_id]
    )
    if duplicate is not None:
        sources = [duplicate.source or {}]
        sources.extend((duplicate.source or {}).get("sources", []))
        by_url = {item.get("url"): item for item in sources if item.get("url")}
        by_url[source["url"]] = source
        primary = dict(sources[0]) if sources else {}
        primary["sources"] = list(by_url.values())
        duplicate.source = primary
        session.flush()
        return duplicate, False
    shared_duplicate = find_duplicate_recipe(
        draft, [recipe for recipe in existing if recipe.owner_household_id is None]
    )
    if shared_duplicate is not None:
        return shared_duplicate, False

    stem = normalize_recipe_title(draft.title).replace(" ", "-")[:90].strip("-") or "external-recipe"
    digest_input = json.dumps(
        [household_id, normalize_recipe_title(draft.title), sorted(ingredient_names)], ensure_ascii=False
    )
    digest = sha256(digest_input.encode()).hexdigest()[:24]
    slug = f"external-{stem}-{digest}"[:160]
    nutrients = draft.nutrition_per_serving
    known_allergens = sorted({allergen for line in draft.ingredients for allergen in (line.allergens or [])})
    halal_values = {line.halal_status for line in draft.ingredients}
    halal_status = (
        "not_halal"
        if "not_halal" in halal_values
        else "needs_certification"
        if "needs_certification" in halal_values
        else "uncertain"
        if None in halal_values or "uncertain" in halal_values
        else "halal"
    )
    recipe = Recipe(
        slug=slug,
        title=draft.title,
        description=f"Privately added recipe: {draft.title}",
        cuisine=draft.cuisine or "international",
        meal_type=draft.course,
        servings=draft.servings,
        prep_time_minutes=draft.prep_time_minutes,
        cook_time_minutes=draft.cook_time_minutes,
        dietary_tags=[],
        course=draft.course,
        meal_types=list(draft.meal_types),
        difficulty=draft.difficulty,
        passive_time_minutes=draft.passive_time_minutes,
        time_basis=draft.time_basis,
        servings_basis=draft.servings_basis,
        allergens=known_allergens,
        source=source,
        halal_status=halal_status,
        unknown_safety=["diet" if item == "dietary_tags" else item for item in review.unknown_safety],
        **tags.values,
        estimated={
            name: {"method": "rule", "reviewed": True, "batch": "external-intake-rule-v1"} for name in tags.values
        },
        owner_household_id=household_id,
        nutrition=RecipeNutrition(
            **{
                key: Decimal(str(nutrients[key]))
                for key in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
            }
        ),
        steps=[RecipeStep(step_number=index, instruction=step) for index, step in enumerate(draft.steps, start=1)],
    )
    try:
        with session.begin_nested():
            recipe.recipe_ingredients = [
                RecipeIngredient(
                    ingredient=ingredients[line.canonical_id],
                    quantity=Decimal(str(line.grams)),
                    unit="g",
                    grams=Decimal(str(line.grams)),
                    original_text=line.source_name,
                    sort_order=index,
                    provenance={"source": "external-intake", "match_confidence": line.match_confidence},
                )
                for index, line in enumerate(draft.ingredients, start=1)
            ]
            session.add(recipe)
            session.flush()
    except IntegrityError:
        # A concurrent import of the same household/title/ingredient identity may win the unique slug.
        winner = session.scalar(select(Recipe).where(Recipe.slug == slug, Recipe.owner_household_id == household_id))
        if winner is None or find_duplicate_recipe(draft, [winner]) is None:
            raise
        return winner, False
    return recipe, True
