"""Product requests, not held-out episodes: exercise the acceptance boundary."""

import json
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.db.session import get_db_session
from app.main import app
from app.models.meal_plan import MealPlan
from app.models.platform import OperationRun
from app.planning.beam_planner import BeamLimits
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.product_path import ProductPlanningEngine
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from tests.test_recipes import recipe_client as recipe_client

REQUEST = {"start_date": "2026-09-20", "household_size": 2, "pricing_mode": "fixture"}


@contextmanager
def database():
    generator = app.dependency_overrides[get_db_session]()
    try:
        yield next(generator)
    finally:
        generator.close()


def latest_trace():
    with database() as session:
        run = session.scalars(
            select(OperationRun).where(OperationRun.run_type == "planning").order_by(OperationRun.id.desc())
        ).first()
        assert run is not None
        assert run.triggered_by_user_id is not None
        assert run.household_id is not None
        return run, run.artifact_references[0]["data"]


@pytest.mark.parametrize("strategy", ["beam", "greedy-baseline"])
def test_real_request_persists_validated_snapshot_and_trace(recipe_client, monkeypatch, strategy):
    def refetch(*args, **kwargs):
        pytest.fail("A validated basket must not be repriced")

    monkeypatch.setattr(WeeklyGroceryAggregator, "estimate", refetch)
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "planner_strategy": strategy})
    assert response.status_code == 201, response.text
    plan = response.json()
    run, trace = latest_trace()
    assert run.status == "succeeded"
    assert trace["algorithm"] == strategy
    assert trace["validation"]["status"] == "passed"
    assert trace["validation"]["purchase_total_sgd"] == plan["grocery_estimate"]["purchase_total_sgd"]
    assert {"kind": "meal_plan", "id": plan["id"]} in run.artifact_references
    assert len(trace["packet_digest"]) == 64
    assert recipe_client.get(f"/api/plans/{plan['id']}").json() == plan


def test_search_limit_is_not_infeasibility_and_does_not_save_a_plan(recipe_client, monkeypatch):
    original = ProductPlanningEngine.__init__

    def limited(self, **kwargs):
        original(self, limits=BeamLimits(width=1, max_expansions=1))

    monkeypatch.setattr(ProductPlanningEngine, "__init__", limited)
    response = recipe_client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == 422
    run, trace = latest_trace()
    assert run.status == "failed"
    assert trace["status"] == "candidate_rejected"
    assert trace["evidence"] == "bounded_search_exhausted"
    assert trace["search"]["exhausted"] is True
    assert "relax" not in response.text
    with database() as session:
        assert session.scalars(select(MealPlan)).all() == []


@pytest.mark.parametrize("damage", ["packages", "cost", "demand", "source"])
def test_independent_validator_rejects_corrupt_planner_output(recipe_client, monkeypatch, damage):
    original = FinalScopeReferencePlanner._build_shopping

    def corrupted(self, problem, assignments):
        if damage == "source":
            for recipe in problem.recipes:
                recipe.ingredients[0].quantity *= 2
        basket = original(self, problem, assignments)
        if damage == "packages":
            basket[0].packages += 1
        elif damage == "cost":
            basket[0].purchase_cost_sgd += 1
        elif damage == "demand":
            basket[0].required_quantity += 1
        return basket

    monkeypatch.setattr(FinalScopeReferencePlanner, "_build_shopping", corrupted)
    response = recipe_client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["validation"]["status"] == "failed"
    assert trace["status"] != "infeasible"
    with database() as session:
        assert session.scalars(select(MealPlan)).all() == []


def test_missing_prices_fail_closed(recipe_client):
    from app.models.recipe import RecipeIngredient

    with database() as session:
        for row in session.scalars(select(RecipeIngredient)):
            row.unit = "unmapped-unit"
        session.commit()
    response = recipe_client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "needs_data"
    assert trace["evidence"] == "needs_data"


def test_subcent_budget_requires_clarification(recipe_client):
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "weekly_budget_sgd": 40.001})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "needs_clarification"


def test_exhaustive_budget_proof_is_limited_to_the_input_packet(recipe_client):
    response = recipe_client.post(
        "/api/plans/generate", json={**REQUEST, "allergens": ["soy"], "weekly_budget_sgd": 0.01}
    )
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "infeasible"
    assert trace["evidence"] == "exhaustively_infeasible"
    assert trace["proof_scope"] == "supplied_candidate_packet_only"


def test_unknown_allergen_is_missing_evidence(recipe_client):
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "allergens": ["not-in-reviewed-vocabulary"]})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "needs_data"


def test_compiler_proves_a_blocked_slot_even_if_upstream_filter_is_wrong(recipe_client, monkeypatch):
    from app.services.recommendation import RecipeRecommendationService

    original = RecipeRecommendationService.recommend

    def faulty_admission(self, constraints, **kwargs):
        return original(self, constraints.model_copy(update={"max_cooking_time_minutes": 240}), **kwargs)

    monkeypatch.setattr(RecipeRecommendationService, "recommend", faulty_admission)
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "max_cooking_time_minutes": 20})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "infeasible"
    assert trace["evidence"] == "exactly_infeasible"


def test_one_cent_below_the_only_basket_is_rejected(recipe_client):
    request = {**REQUEST, "allergens": ["soy"]}
    plan = recipe_client.post("/api/plans/generate", json=request).json()
    amount = plan["grocery_estimate"]["purchase_total_sgd"]
    response = recipe_client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": round(amount - 0.01, 2)})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["evidence"] == "exhaustively_infeasible"


def test_duplicate_pantry_entries_require_clarification(recipe_client):
    item = {"normalized_name": "chicken_breast", "quantity": 100, "unit": "g"}
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "available_ingredients": [item, item]})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert trace["status"] == "needs_clarification"


def test_per_meal_cost_is_recomputed_even_if_upstream_admits_a_bad_candidate(recipe_client, monkeypatch):
    from app.services.recommendation import RecipeRecommendationService

    original = RecipeRecommendationService.recommend

    def faulty_admission(self, constraints, **kwargs):
        return original(self, constraints.model_copy(update={"budget_per_meal_sgd": None}), **kwargs)

    monkeypatch.setattr(RecipeRecommendationService, "recommend", faulty_admission)
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "budget_per_meal_sgd": 0.01})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert any(c["code"] == "per_meal_budget" and c["status"] == "failed" for c in trace["validation"]["checks"])


def test_default_request_with_repository_catalog(recipe_client):
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog

    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    with database() as session:
        import_catalog(session, catalog)
    response = recipe_client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == 201, response.text
    _, trace = latest_trace()
    assert trace["validation"]["status"] == "passed"


def test_a_full_catalog_week_has_seven_different_dinners(recipe_client):
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog

    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    with database() as session:
        import_catalog(session, catalog)
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "weekly_budget_sgd": None})
    assert response.status_code == 201, response.text
    days = response.json()["days"]
    assert len({day["recipe"]["slug"] for day in days}) == 7
    # The catalog's breakfast bowl never fills a dinner while dinners are available.
    assert all(day["recipe"]["meal_type"] != "breakfast" for day in days)
    _, trace = latest_trace()
    assert trace.get("meal_type_filtered", 0) >= 1


def test_trace_contains_no_plaintext_health_profile(recipe_client):
    response = recipe_client.post(
        "/api/plans/generate", json={**REQUEST, "allergens": ["soy"], "max_sodium_mg_per_meal": 619}
    )
    assert response.status_code == 201
    _, trace = latest_trace()
    # ADR-0047: the full request is kept on purpose under "request" so the console can replay the run
    # (a saved plan already keeps it in meal_plans.constraints); the rest of the trace stays verdicts only.
    assert trace["request"]["allergens"] == ["soy"]
    encoded = json.dumps({key: value for key, value in trace.items() if key != "request"})
    assert '"soy"' not in encoded
    assert '"allergens"' not in encoded
    assert '"nutrition_targets"' not in encoded
    for check in trace["validation"]["checks"]:
        assert not {"actual", "limit", "detail"}.intersection(check)


def test_same_snapshot_and_settings_produce_same_plan(recipe_client, monkeypatch):
    from datetime import UTC, datetime

    from app.products import provider

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 20, tzinfo=UTC)

    monkeypatch.setattr(provider, "datetime", FrozenDatetime)
    first = recipe_client.post("/api/plans/generate", json=REQUEST).json()
    _, first_trace = latest_trace()
    second = recipe_client.post("/api/plans/generate", json=REQUEST).json()
    _, second_trace = latest_trace()
    assert [d["recipe"]["slug"] for d in first["days"]] == [d["recipe"]["slug"] for d in second["days"]]
    assert first_trace == second_trace


def test_plan_and_trace_rollback_together_on_storage_error(recipe_client, monkeypatch):
    from sqlalchemy.orm import Session

    original = Session.commit

    def fail_plan_commit(session):
        if any(isinstance(obj, OperationRun) and obj.run_type == "planning" for obj in session.new):
            raise RuntimeError("synthetic storage failure")
        original(session)

    monkeypatch.setattr(Session, "commit", fail_plan_commit)
    with pytest.raises(RuntimeError, match="synthetic storage failure"):
        recipe_client.post("/api/plans/generate", json=REQUEST)
    with database() as session:
        assert session.scalars(select(MealPlan)).all() == []
        assert session.scalars(select(OperationRun).where(OperationRun.run_type == "planning")).all() == []


def test_a_budget_below_the_best_ranked_week_is_still_planned(recipe_client):
    """The ranking never sees prices; with a budget the packet and a cost-led fallback search do."""
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog

    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    with database() as session:
        import_catalog(session, catalog)
    free = recipe_client.post("/api/plans/generate", json=REQUEST).json()["grocery_estimate"]["purchase_total_sgd"]

    budget = 60  # about two thirds of the best-ranked week (S$89.20 on this catalog)
    assert free > budget
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "weekly_budget_sgd": budget})
    assert response.status_code == 201, response.text
    assert response.json()["grocery_estimate"]["purchase_total_sgd"] <= budget

    too_low = recipe_client.post("/api/plans/generate", json={**REQUEST, "weekly_budget_sgd": 20})
    assert too_low.status_code == 422
    assert "couldn't fit seven dinners into S$20.00" in too_low.json()["detail"]


def test_the_default_household_week_is_dinner_with_a_main_and_a_vegetable(recipe_client):
    """A profile that sets no shape plans ADR-0046's default; lunch added by shape plans lunches too."""
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog
    from app.schemas.meal_plan import MEAL_PRESETS, default_plan_shape

    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    with database() as session:
        import_catalog(session, catalog)
    shape = default_plan_shape().model_dump(mode="json")
    assert list(shape["meals"]) == ["dinner"]
    assert [role["role_id"] for role in shape["meals"]["dinner"]] == ["main", "vegetable"]

    both = {"meals": {"lunch": MEAL_PRESETS["lunch"]["one dish"], "dinner": [{"role_id": "main", "courses": ["main"]}]}}
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "plan_shape": both})
    assert response.status_code == 201, response.text
    meals = {(d["day_index"], d["meal_type"]) for d in response.json()["days"]}
    assert meals == {(day, meal) for day in range(1, 8) for meal in ("lunch", "dinner")}
