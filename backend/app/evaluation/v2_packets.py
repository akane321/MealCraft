"""Compile leakage-resistant developer packets for Evaluation v2.

The compiler shares reviewed facts, not MealCraft intermediate answers. These
developer packets exercise the contract only; independent held-out episodes
must be authored and frozen before comparative claims are reported.
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.paths import repository_root


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacketConversationTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: str


class PacketHouseholdProfile(StrictModel):
    household_size: int | None = Field(default=None, ge=1, le=12)
    allergens: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)


class PacketPantryItem(StrictModel):
    ingredient_id: str
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None


class PacketPlanningHorizon(StrictModel):
    start_date: str
    slots: list[str]


class PacketLockedMeal(StrictModel):
    slot: str
    recipe_id: str
    status: Literal["locked", "completed"]


class PacketIngredient(StrictModel):
    ingredient_id: str
    quantity: float
    unit: str
    preparation: str | None
    allergen: str | None


class PacketNutrition(StrictModel):
    calories_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    sodium_mg: float
    sugar_g: float
    complete: bool


class PacketRecipeCandidate(StrictModel):
    recipe_id: str
    title: str
    servings: int
    total_time_minutes: int
    cuisine: str
    meal_type: str
    dietary_tags: list[str]
    ingredients: list[PacketIngredient]
    nutrition_per_serving: PacketNutrition
    source_reference: str


class PacketProductObservation(StrictModel):
    provider_product_id: str
    raw_title: str
    mapped_ingredient_ids: list[str]
    brand: str
    category: str
    package_quantity: float
    package_unit: str
    observed_price_sgd: float
    available: bool
    source_url: str
    provider_mode: Literal["fixture", "frozen_live"]
    observed_at: datetime


class FrozenEvaluationPacket(StrictModel):
    scenario_id: str
    scenario_category: str
    user_request: str
    conversation_history: list[PacketConversationTurn]
    household_profile: PacketHouseholdProfile
    pantry: list[PacketPantryItem]
    planning_horizon: PacketPlanningHorizon
    locked_or_completed_meals: list[PacketLockedMeal]
    recipe_candidates: list[PacketRecipeCandidate]
    fairprice_snapshot: list[PacketProductObservation]
    output_schema_version: Literal["evaluation-output-v2"] = "evaluation-output-v2"
    policy_version: Literal["planning-policy-v2"] = "planning-policy-v2"


class PacketSourceScenario(StrictModel):
    scenario_id: str
    scenario_category: str
    user_request: str
    conversation_history: list[PacketConversationTurn] = Field(default_factory=list)
    household_profile: PacketHouseholdProfile = Field(default_factory=PacketHouseholdProfile)
    pantry: list[PacketPantryItem] = Field(default_factory=list)
    planning_horizon: PacketPlanningHorizon
    locked_or_completed_meals: list[PacketLockedMeal] = Field(default_factory=list)
    recipe_candidate_slugs: list[str]
    fairprice_product_ids: list[str]


class PacketSourceFile(StrictModel):
    schema_version: Literal["packet-source-v1"]
    evaluation_role: Literal["developer_set", "held_out_set"]
    provider_mode: Literal["fixture", "frozen_live"]
    observed_at: datetime
    scenarios: list[PacketSourceScenario]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compile_packets(
    source: PacketSourceFile,
    *,
    ingredients: dict[str, Any],
    recipes: dict[str, Any],
    products: dict[str, Any],
) -> list[FrozenEvaluationPacket]:
    """Turn source scenarios into frozen packets, or fail loudly.

    Separated from file loading so that a caller holding a `PacketSourceFile` in
    memory - the held-out compiler builds one from authored episodes - reuses
    this logic rather than copying it. Two implementations would drift, and a
    packet compiled by the second is not comparable to one compiled by the first.
    """
    packets: list[FrozenEvaluationPacket] = []

    for scenario in source.scenarios:
        unknown_recipes = sorted(set(scenario.recipe_candidate_slugs) - recipes.keys())
        unknown_products = sorted(set(scenario.fairprice_product_ids) - products.keys())
        if unknown_recipes:
            raise ValueError(f"unknown recipe candidates: {', '.join(unknown_recipes)}")
        if unknown_products:
            raise ValueError(f"unknown FairPrice products: {', '.join(unknown_products)}")

        recipe_candidates: list[PacketRecipeCandidate] = []
        for slug in scenario.recipe_candidate_slugs:
            recipe = recipes[slug]
            recipe_ingredients: list[PacketIngredient] = []
            for item in recipe["ingredients"]:
                ingredient = ingredients.get(item["ingredient"])
                if ingredient is None:
                    raise ValueError(f"recipe {slug} references unknown ingredient {item['ingredient']}")
                recipe_ingredients.append(
                    PacketIngredient(
                        ingredient_id=item["ingredient"],
                        quantity=item["quantity"],
                        unit=item["unit"],
                        preparation=item.get("preparation"),
                        allergen=ingredient.get("allergen"),
                    )
                )
            nutrition = recipe["nutrition"]
            recipe_candidates.append(
                PacketRecipeCandidate(
                    recipe_id=slug,
                    title=recipe["title"],
                    servings=recipe["servings"],
                    total_time_minutes=recipe["prep_time_minutes"] + recipe["cook_time_minutes"],
                    cuisine=recipe["cuisine"],
                    meal_type=recipe["meal_type"],
                    dietary_tags=recipe["dietary_tags"],
                    ingredients=recipe_ingredients,
                    nutrition_per_serving=PacketNutrition(**nutrition, complete=True),
                    source_reference=f"data/recipes/recipes.json#{slug}",
                )
            )

        product_observations = [
            PacketProductObservation(
                provider_product_id=products[product_id]["external_id"],
                raw_title=products[product_id]["name"],
                mapped_ingredient_ids=products[product_id]["ingredient_keys"],
                brand=products[product_id]["brand"],
                category=products[product_id]["category"],
                package_quantity=products[product_id]["package_size"],
                package_unit=products[product_id]["package_unit"],
                observed_price_sgd=products[product_id]["price_sgd"],
                available=products[product_id].get("in_stock", True),
                source_url=products[product_id]["product_url"],
                provider_mode=source.provider_mode,
                observed_at=source.observed_at,
            )
            for product_id in scenario.fairprice_product_ids
        ]
        candidate_ingredient_ids = {
            ingredient.ingredient_id
            for recipe_candidate in recipe_candidates
            for ingredient in recipe_candidate.ingredients
        }
        covered_ingredient_ids = {
            ingredient_id for observation in product_observations for ingredient_id in observation.mapped_ingredient_ids
        }
        missing_product_coverage = sorted(candidate_ingredient_ids - covered_ingredient_ids)
        if missing_product_coverage:
            raise ValueError(
                "FairPrice snapshot does not cover candidate ingredients: " + ", ".join(missing_product_coverage)
            )
        packets.append(
            FrozenEvaluationPacket(
                scenario_id=scenario.scenario_id,
                scenario_category=scenario.scenario_category,
                user_request=scenario.user_request,
                conversation_history=scenario.conversation_history,
                household_profile=scenario.household_profile,
                pantry=scenario.pantry,
                planning_horizon=scenario.planning_horizon,
                locked_or_completed_meals=scenario.locked_or_completed_meals,
                recipe_candidates=recipe_candidates,
                fairprice_snapshot=product_observations,
            )
        )

    return packets


def compile_v2_developer_packets(
    *,
    source_path: Path,
    ingredient_path: Path,
    recipe_path: Path,
    product_path: Path,
) -> dict[str, Any]:
    """Compile selected neutral facts and fail on missing source references."""
    source = PacketSourceFile.model_validate(_load_json(source_path))
    packets = compile_packets(
        source,
        ingredients={item["normalized_name"]: item for item in _load_json(ingredient_path)},
        recipes={item["slug"]: item for item in _load_json(recipe_path)},
        products={item["external_id"]: item for item in _load_json(product_path)},
    )
    packet_payloads = [packet.model_dump(mode="json") for packet in packets]
    return {
        "schema_version": "evaluation-packets-v2-dev-1",
        "evaluation_role": source.evaluation_role,
        "live_api_used": False,
        "source_digests": {
            "scenario_source_sha256": _sha256(source_path),
            "ingredient_catalog_sha256": _sha256(ingredient_path),
            "recipe_catalog_sha256": _sha256(recipe_path),
            "product_snapshot_sha256": _sha256(product_path),
        },
        "packet_count": len(packet_payloads),
        "packet_set_sha256": _canonical_digest(packet_payloads),
        "packets": packet_payloads,
    }


def context_matched_llm_prompt(packet: FrozenEvaluationPacket) -> str:
    """Render a strong one-shot baseline prompt without running a model."""
    instructions = (
        "Use only the supplied packet. Respect hard constraints; ask for necessary missing information; "
        "do not invent recipes, products, prices, quantities or nutrition; account for servings, known pantry "
        "quantities and package rounding; distinguish purchase cost from ingredient-use cost; report "
        "infeasibility truthfully; and return JSON matching evaluation-output-v2. You have no tools and no "
        "post-generation repair."
    )
    return (
        instructions
        + "\n\nEVALUATION_PACKET:\n"
        + json.dumps(packet.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    )


def write_v2_packet_bundle(bundle: dict[str, Any], output_path: Path) -> None:
    """Write a deterministic, reviewable packet bundle."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile Evaluation v2 developer packets")
    parser.add_argument(
        "--source",
        type=Path,
        default=repository_root() / "data/evaluation/v2/dev/packet-source-v1.json",
    )
    parser.add_argument(
        "--ingredients",
        type=Path,
        default=repository_root() / "data/ingredients/ingredients.json",
    )
    parser.add_argument(
        "--recipes",
        type=Path,
        default=repository_root() / "data/recipes/recipes.json",
    )
    parser.add_argument(
        "--products",
        type=Path,
        default=repository_root() / "data/fixtures/fairprice-products.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repository_root() / "data/evaluation/v2/dev/packets-v1.json",
    )
    args = parser.parse_args()
    bundle = compile_v2_developer_packets(
        source_path=args.source,
        ingredient_path=args.ingredients,
        recipe_path=args.recipes,
        product_path=args.products,
    )
    write_v2_packet_bundle(bundle, args.output)
    print(
        f"compiled {bundle['packet_count']} developer packets; "
        f"live_api_used={str(bundle['live_api_used']).lower()}; output={args.output}"
    )


if __name__ == "__main__":
    main()
