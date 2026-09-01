import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data.catalog import Catalog, import_catalog, load_catalog
from app.db.base import Base
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelector
from app.products.provider import FixtureProductProvider
from app.repositories.product import ProductSnapshotRepository
from app.repositories.recipe import RecipeRepository
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.services.product import ProductSearchService
from app.services.recommendation import RecipeRecommendationService


class EvaluationScenario(BaseModel):
    name: str
    expected_feasible: bool
    request: dict[str, Any]


@dataclass
class ScenarioResult:
    name: str
    expected_feasible: bool
    actual_feasible: bool
    selected_slugs: list[str]
    hard_constraint_violations: list[str]
    deterministic: bool
    consecutive_repetitions: int
    grocery_complete: bool | None


def load_scenarios(path: Path) -> list[EvaluationScenario]:
    return [EvaluationScenario.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _product_service(session: Session, fixture_path: Path) -> ProductSearchService:
    return ProductSearchService(
        fixture_provider=FixtureProductProvider(str(fixture_path)),
        live_provider=FixtureProductProvider(str(fixture_path)),
        repository=ProductSnapshotRepository(session),
        cache_ttl_minutes=15,
    )


def _dietary_match(preference: str, tags: set[str]) -> bool:
    if preference == "vegetarian":
        return bool({"vegetarian", "vegan"}.intersection(tags))
    if preference == "dairy-free" and "vegan" in tags:
        return True
    return preference in tags


def _hard_violations(recipe, request: WeeklyMealPlanRequest) -> list[str]:
    violations: list[str] = []
    ingredient_names = {item.ingredient.normalized_name for item in recipe.recipe_ingredients}
    allergens = {item.ingredient.allergen for item in recipe.recipe_ingredients if item.ingredient.allergen}
    if allergens.intersection(request.allergens):
        violations.append("allergen")
    if ingredient_names.intersection(request.excluded_ingredients):
        violations.append("excluded_ingredient")
    if recipe.total_time_minutes > request.max_cooking_time_minutes:
        violations.append("cooking_time")
    if any(not _dietary_match(item, set(recipe.dietary_tags)) for item in request.dietary_preferences):
        violations.append("dietary_preference")
    if (
        request.max_sodium_mg_per_meal is not None
        and float(recipe.nutrition.sodium_mg) > request.max_sodium_mg_per_meal
    ):
        violations.append("sodium")
    return violations


def _fixture_mapping_coverage(catalog: Catalog, fixture_path: Path) -> tuple[int, int, float]:
    records = json.loads(fixture_path.read_text(encoding="utf-8"))
    mapped_keys = {
        key for record in records if record.get("in_stock", True) for key in record.get("ingredient_keys", [])
    }
    used = {item.ingredient for recipe in catalog.recipes for item in recipe.ingredients}
    mapped = len(used.intersection(mapped_keys))
    return mapped, len(used), round(mapped / max(len(used), 1), 4)


def evaluate(
    *,
    ingredient_path: Path,
    recipe_path: Path,
    scenario_path: Path,
    fixture_path: Path,
) -> dict[str, Any]:
    catalog = load_catalog(ingredient_path, recipe_path)
    scenarios = load_scenarios(scenario_path)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    results: list[ScenarioResult] = []
    with Session(engine, expire_on_commit=False) as session:
        import_catalog(session, catalog)
        recipe_repository = RecipeRepository(session)
        product_service = _product_service(session, fixture_path)
        recommendation_service = RecipeRecommendationService(
            recipe_repository,
            grocery_estimator=GroceryEstimator(product_service),
        )
        selector = WeeklyPlanSelector()
        aggregator = WeeklyGroceryAggregator(product_service)

        for scenario in scenarios:
            request = WeeklyMealPlanRequest.model_validate(scenario.request)
            recommendation_result = recommendation_service.recommend(request, deduct_pantry_from_cost=False)
            actual_feasible = bool(recommendation_result.recommendations)
            selected_slugs: list[str] = []
            violations: list[str] = []
            deterministic = True
            repetitions = 0
            grocery_complete: bool | None = None

            if actual_feasible:
                selected, _ = selector.select(recommendation_result.recommendations, request)
                second, _ = selector.select(recommendation_result.recommendations, request)
                selected_slugs = [item.recipe.slug for item in selected]
                deterministic = selected_slugs == [item.recipe.slug for item in second]
                repetitions = sum(
                    left == right for left, right in zip(selected_slugs, selected_slugs[1:], strict=False)
                )
                recipes_by_id = {recipe.id: recipe for recipe in recipe_repository.list_for_recommendation()}
                selected_recipes = [recipes_by_id[item.recipe.id] for item in selected]
                for day, recipe in enumerate(selected_recipes, start=1):
                    violations.extend(f"day_{day}:{item}" for item in _hard_violations(recipe, request))
                grocery_complete = aggregator.estimate(selected_recipes, request).complete

            results.append(
                ScenarioResult(
                    name=scenario.name,
                    expected_feasible=scenario.expected_feasible,
                    actual_feasible=actual_feasible,
                    selected_slugs=selected_slugs,
                    hard_constraint_violations=violations,
                    deterministic=deterministic,
                    consecutive_repetitions=repetitions,
                    grocery_complete=grocery_complete,
                )
            )

    mapped, used, mapping_coverage = _fixture_mapping_coverage(catalog, fixture_path)
    expectation_matches = sum(item.expected_feasible == item.actual_feasible for item in results)
    feasible_results = [item for item in results if item.expected_feasible]
    metrics = {
        "catalog_recipe_count": len(catalog.recipes),
        "catalog_ingredient_count": len(catalog.ingredients),
        "scenario_count": len(results),
        "scenario_expectation_rate": round(expectation_matches / max(len(results), 1), 4),
        "feasible_scenario_success_rate": round(
            sum(item.actual_feasible for item in feasible_results) / max(len(feasible_results), 1), 4
        ),
        "hard_constraint_violation_count": sum(len(item.hard_constraint_violations) for item in results),
        "determinism_rate": round(sum(item.deterministic for item in results) / max(len(results), 1), 4),
        "consecutive_repetition_count": sum(item.consecutive_repetitions for item in results),
        "fixture_mapping_count": mapped,
        "used_ingredient_count": used,
        "fixture_mapping_coverage": mapping_coverage,
        "complete_grocery_rate": round(
            sum(item.grocery_complete is True for item in feasible_results) / max(len(feasible_results), 1), 4
        ),
    }
    thresholds = {
        "catalog_recipe_count": metrics["catalog_recipe_count"] >= 30,
        "scenario_expectation_rate": metrics["scenario_expectation_rate"] >= 0.95,
        "feasible_scenario_success_rate": metrics["feasible_scenario_success_rate"] >= 0.95,
        "hard_constraint_violation_count": metrics["hard_constraint_violation_count"] == 0,
        "determinism_rate": metrics["determinism_rate"] == 1.0,
        "consecutive_repetition_count": metrics["consecutive_repetition_count"] == 0,
        "fixture_mapping_coverage": metrics["fixture_mapping_coverage"] >= 0.95,
        "complete_grocery_rate": metrics["complete_grocery_rate"] >= 0.95,
    }
    return {
        "passed": all(thresholds.values()),
        "metrics": metrics,
        "thresholds": thresholds,
        "scenarios": [asdict(item) for item in results],
    }


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "# MealCraft MVP Evaluation",
        "",
        f"**Overall result: {status}**",
        "",
        "## Metrics",
        "",
        "| Metric | Result | Gate |",
        "|---|---:|:---:|",
    ]
    for name, value in report["metrics"].items():
        gate = report["thresholds"].get(name)
        lines.append(f"| `{name}` | {value} | {'PASS' if gate is True else 'FAIL' if gate is False else '-'} |")
    lines.extend(["", "## Scenario results", "", "| Scenario | Expected | Actual | Violations |", "|---|---|---|---:|"])
    for item in report["scenarios"]:
        lines.append(
            f"| {item['name']} | {'feasible' if item['expected_feasible'] else 'rejected'} | "
            f"{'feasible' if item['actual_feasible'] else 'rejected'} | {len(item['hard_constraint_violations'])} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
