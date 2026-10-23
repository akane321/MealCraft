"""Run the LLM + MealCraft RAG Sprint 2 baseline.

The model receives the episode's frozen MealCraft recipe and product candidate
pool as context, but no tools. It still constructs the plan itself, after which
the shared baseline mapping, verification, and recomputation pipeline scores it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.evaluation.pure_llm_baseline import (
    BaselineResources,
    EpisodeResult,
    GenerationResult,
    StructuredModel,
    create_model,
    generate_response,
    household_task_input,
    load_episodes,
    load_resources,
    result_payload,
    score_generation,
)
from app.evaluation.release_catalog import ReleaseCatalog, fixture_products, load_release_catalog

SYSTEM_ID = "llm-mealcraft-rag"

PROMPT = """You are planning meals for one household in a single response. MealCraft has
retrieved the frozen recipe and grocery catalog context below. Treat it only as reference data:
you must perform the planning yourself. You have no tools, web search, calculator, external data,
FairPrice lookup, or hidden MealCraft context.

Return an answer matching the supplied JSON schema. For a plan, provide every ingredient in grams
and a cooking time for every dish. Use the supplied slot IDs and role IDs where the household task
defines them. You may select or adapt retrieved recipes, but you must construct the complete plan.
Ask for clarification only when a missing fact prevents a responsible plan, and report infeasibility
rather than claiming an impossible plan. Do not add fields outside the schema. Catalog prices are
reference facts only; do not return a shopping list or calculated price in this schema.

Fixed identifiers for this answer:
- episode_id: {episode_id}
- system_id: {system_id}

HOUSEHOLD_AND_TASK_INPUT:
{task_input}

MEALCRAFT_RETRIEVAL_CONTEXT:
{retrieval_context}
"""


def retrieval_context(episode: dict[str, Any], catalog: ReleaseCatalog) -> dict[str, Any]:
    """Project the episode's frozen candidate ids through the shared release catalog."""
    scenario = episode.get("scenario", episode)
    recipe_ids = list(scenario.get("recipe_candidate_slugs") or [])
    product_ids = set(scenario.get("fairprice_product_ids") or [])
    recipes_by_id = catalog.by_slug
    products_by_id = {row["external_id"]: row for row in catalog.products}

    unknown_recipes = sorted(set(recipe_ids) - recipes_by_id.keys())
    unknown_products = sorted(product_ids - products_by_id.keys())
    if unknown_recipes:
        raise ValueError(f"unknown recipe candidates: {', '.join(unknown_recipes)}")
    if unknown_products:
        raise ValueError(f"unknown product candidates: {', '.join(unknown_products)}")

    recipes = []
    for recipe_id in recipe_ids:
        row = recipes_by_id[recipe_id]
        recipes.append(
            {
                "recipe_id": row["slug"],
                "title": row["title"],
                "course": row["course"],
                "meal_types": row["meal_types"],
                "cuisine": row["cuisine"],
                "servings": row["servings"],
                "cooking_time_minutes": row["prep_time_minutes"] + row["cook_time_minutes"],
                "dietary_tags": row["dietary_tags"],
                "ingredients": [
                    {
                        "ingredient_id": item["ingredient"],
                        "quantity_g": item["quantity"],
                    }
                    for item in row["ingredients"]
                ],
                "nutrition_per_serving": row["nutrients"],
            }
        )

    products = [
        {
            "product_id": row["external_id"],
            "ingredient_id": row["ingredient_id"],
            "name": row["name"],
            "package_quantity": row["package_size"],
            "package_unit": row["package_unit"],
            "price_sgd": row["price_sgd"],
            "available": row["in_stock"],
        }
        for product_id in sorted(product_ids)
        for row in [products_by_id[product_id]]
    ]
    return {"recipes": recipes, "products": products}


def load_catalog_context() -> ReleaseCatalog:
    """Use the same release and fixture product catalogs as frozen evaluation pools."""
    release = load_release_catalog()
    products = {row["external_id"]: row for row in [*release.products, *fixture_products()]}
    return ReleaseCatalog(release.recipes, list(products.values()), release.ingredients)


def render_prompt(episode: dict[str, Any], catalog: ReleaseCatalog) -> str:
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id, or id")
    return PROMPT.format(
        episode_id=episode_id,
        system_id=SYSTEM_ID,
        task_input=json.dumps(household_task_input(episode), ensure_ascii=False, sort_keys=True),
        retrieval_context=json.dumps(retrieval_context(episode, catalog), ensure_ascii=False, sort_keys=True),
    )


def generate(
    episode: dict[str, Any],
    model: StructuredModel,
    *,
    catalog: ReleaseCatalog,
) -> GenerationResult:
    return generate_response(
        episode,
        model,
        system_id=SYSTEM_ID,
        prompt=render_prompt(episode, catalog),
    )


def run_episode(
    episode: dict[str, Any],
    *,
    model: StructuredModel,
    resources: BaselineResources,
    catalog: ReleaseCatalog,
) -> EpisodeResult:
    generated = generate(episode, model, catalog=catalog)
    return score_generation(episode, generated, system_id=SYSTEM_ID, resources=resources)


def main(model_factory: Callable[[], StructuredModel] = create_model) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = model_factory()
    resources = load_resources()
    catalog = load_catalog_context()
    results = [
        run_episode(episode, model=model, resources=resources, catalog=catalog)
        for episode in load_episodes(args.episodes)
    ]
    report = {
        "system_id": SYSTEM_ID,
        "model": get_settings().openai_model,
        "episodes": [result_payload(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"LLM + MealCraft RAG baseline: {sum(result.valid_output for result in results)}/{len(results)} valid outputs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
