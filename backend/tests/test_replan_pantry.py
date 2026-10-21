from types import SimpleNamespace as NS

import pytest

from app.api.routes.meal_plans import build_meal_plan_service
from app.db.session import get_db_session
from app.main import app
from app.planning.replan_pantry import remaining_stock
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.recommendation import AvailableIngredientInput
from tests.test_planning_capability import _dish, dish_client


def line(*, used=0, extra=None, unit="g", package_unit="g"):
    return NS(
        ingredient_name="firm_tofu",
        pantry_deduction=used,
        unit=unit,
        excess_quantity=extra,
        product=NS(package_unit=package_unit) if extra is not None else None,
    )


def test_stock_reserves_pantry_and_converts_package_surplus_without_mutation():
    pantry = [AvailableIngredientInput(normalized_name="firm_tofu", quantity=1, unit="kg")]
    result = remaining_stock(pantry, NS(items=[line(used=400, extra=200)]))
    assert result[0].quantity == pytest.approx(0.8)
    assert result[0].unit == "kg"
    assert pantry[0].quantity == 1


def test_same_pantry_is_reserved_across_multiple_lines():
    pantry = [AvailableIngredientInput(normalized_name="firm_tofu", quantity=500, unit="g")]
    assert remaining_stock(pantry, NS(items=[line(used=200), line(used=300)])) == []


def test_unknown_stock_is_not_invented_and_known_surplus_can_still_be_used():
    pantry = [AvailableIngredientInput(normalized_name="firm_tofu")]
    assert remaining_stock(pantry, NS(items=[line()]))[0].quantity is None
    assert remaining_stock(pantry, NS(items=[line(extra=50)]))[0].quantity == 50


@pytest.mark.parametrize("pantry_grams", [0, 40, 500])
def test_free_addition_uses_reserved_package_surplus_or_unspent_pantry(monkeypatch, pantry_grams):
    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2,
                weekly_budget_sgd=10,
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
                available_ingredients=(
                    [{"normalized_name": "firm_tofu", "quantity": pantry_grams, "unit": "g"}] if pantry_grams else []
                ),
            )
            # The unchanged dinner has reserved a package; a second 50 g serving needs no new package.
            rest = [(recipe, 1)]
            before = service.grocery_aggregator.estimate([recipe], request, shares=[1])
            after = service.grocery_aggregator.estimate([recipe, recipe], request, shares=[1, 1])
            assert before.complete and after.complete
            assert after.purchase_total_sgd == before.purchase_total_sgd
            modes = []
            plan = service.planning_engine.plan

            def record(*args, **kwargs):
                modes.append(kwargs["budget_is_hard"])
                return plan(*args, **kwargs)

            monkeypatch.setattr(service.planning_engine, "plan", record)
            result = service.plan_dishes(
                request.model_copy(update={"weekly_budget_sgd": 0}), first_day=2, day_count=1, rest=rest, over_budget=1
            )
            assert len(result) == 1
            assert modes and all(modes)
            assert request.available_ingredients == (
                []
                if not pantry_grams
                else [AvailableIngredientInput(normalized_name="firm_tofu", quantity=pantry_grams, unit="g")]
            )
        finally:
            database.close()


def test_pantry_used_by_unchanged_dinner_cannot_pay_for_added_dinner(monkeypatch):
    from app.planning.product_path import ProductPlanningError

    dish = _dish("tofu-dinner", "main", "firm_tofu", 1000, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2,
                weekly_budget_sgd=0.01,
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
                available_ingredients=[{"normalized_name": "firm_tofu", "quantity": 500, "unit": "g"}],
            )
            with pytest.raises(ProductPlanningError):
                service.plan_dishes(request, first_day=2, day_count=1, rest=[(recipe, 1)])
            # An explicit addition can still be previewed over budget; nothing is saved here.
            offered = service.plan_dishes(request, first_day=2, day_count=1, rest=[(recipe, 1)], over_budget=1)
            assert len(offered) == 1
            basket = service.grocery_aggregator.estimate([recipe, recipe], request, shares=[1, 1])
            assert basket.purchase_total_sgd > request.weekly_budget_sgd
        finally:
            database.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_whole_basket_is_checked_even_if_partial_search_accepts(monkeypatch, unknown):
    from app.planning.product_path import ProductPlanningError

    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2, weekly_budget_sgd=100, meal_composition=[{"role_id": "main", "courses": ["main"]}]
            )
            estimate = service.grocery_aggregator.estimate
            reserved = estimate([recipe], request, shares=[1]).purchase_total_sgd

            def checked(recipes, constraints, **kwargs):
                result = estimate(recipes, constraints, **kwargs)
                if len(recipes) == 2:
                    result = result.model_copy(
                        update=({"complete": False} if unknown else {"purchase_total_sgd": reserved + 100.01})
                    )
                return result

            monkeypatch.setattr(service.grocery_aggregator, "estimate", checked)
            with pytest.raises(ProductPlanningError, match="whole week"):
                service.plan_dishes(request, first_day=2, day_count=1, rest=[(recipe, 1)])
        finally:
            database.close()


@pytest.mark.parametrize("days", [[2, 9], [9], [2]])
@pytest.mark.parametrize("pantry_grams", [0, 80, 500])
def test_two_trips_reserve_stock_once_and_keep_calendar_days(monkeypatch, days, pantry_grams):
    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2,
                day_count=14,
                weekly_budget_sgd=100,
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
                available_ingredients=(
                    [{"normalized_name": "firm_tofu", "quantity": pantry_grams, "unit": "g"}] if pantry_grams else []
                ),
            )
            original = request.model_dump()
            observed = []
            plan = service.planning_engine.plan

            def record(constraints, *args, **kwargs):
                observed.append(
                    (
                        constraints.start_date,
                        [(p.quantity, p.unit) for p in constraints.available_ingredients],
                        kwargs["budget_is_hard"],
                    )
                )
                return plan(constraints, *args, **kwargs)

            monkeypatch.setattr(service.planning_engine, "plan", record)
            results = service.plan_dishes(
                request,
                first_day=min(days),
                day_count=len(days),
                day_indices=days,
                rest=[(recipe, 1), (recipe, 1)],
                rest_days=[1, 8],
                over_budget=10,
            )
            assert [d.day_index for d in results] == days
            assert [(d.planned_date - request.start_date).days + 1 for d in results] == days
            assert observed and all(row[2] for row in observed)
            assert request.model_dump() == original
            # Independent canonical two-trip basket: original pantry is consumed only once.
            full = service.grocery_aggregator.estimate(
                [recipe] * (2 + len(days)),
                request,
                shares=[1] * (2 + len(days)),
                trips=[1, 2] + [1 if d <= 7 else 2 for d in days],
            )
            assert full.complete and full.within_weekly_budget
            if pantry_grams == 80 and 9 in days:
                # Day 1 and day 2 consume all original stock; trip 2 gets only its own package surplus.
                if 2 in days:
                    second = [row for row in observed if (row[0] - request.start_date).days >= 7]
                    reserved = service.grocery_aggregator.estimate(
                        [recipe], request.model_copy(update={"available_ingredients": []}), shares=[1]
                    )
                    assert second[-1][1][0][0] == reserved.items[0].excess_quantity
        finally:
            database.close()


def test_second_trip_surplus_cannot_pay_for_first_trip(monkeypatch):
    from app.planning.product_path import ProductPlanningError

    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2,
                day_count=14,
                weekly_budget_sgd=0.01,
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
            )
            with pytest.raises(ProductPlanningError):
                service.plan_dishes(request, first_day=1, day_count=1, rest=[(recipe, 1)], rest_days=[8])
        finally:
            database.close()


def test_two_trip_shape_preview_reaches_trip_cost_path(monkeypatch):
    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]) as client:
        generated = client.post(
            "/api/plans/generate",
            json={
                "household_size": 2,
                "day_count": 14,
                "weekly_budget_sgd": 100,
                "meal_composition": [{"role_id": "main", "courses": ["main"]}],
            },
        )
        assert generated.status_code == 201, generated.text
        plan = generated.json()
        response = client.post(
            f"/api/plans/{plan['id']}/shape/preview",
            json={"meal_type": "lunch", "roles": [{"role_id": "main", "courses": ["main"]}], "day_indexes": [2, 9]},
        )
        assert response.status_code == 201, response.text
        assert response.json()["shape_change"]["day_indexes"] == [2, 9]
        # Preview never saves its additional meals.
        saved = client.get(f"/api/plans/{plan['id']}")
        assert saved.status_code == 200
        assert len(saved.json()["days"]) == len(plan["days"])


@pytest.mark.parametrize("cents_short", [0, 1])
def test_each_trip_has_its_own_exact_checkout_limit(monkeypatch, cents_short):
    from app.planning.product_path import ProductPlanningError

    dish = _dish("tofu-dinner", "main", "firm_tofu", 100, calories=400)
    with dish_client(monkeypatch, [dish]):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            recipe = service.recipe_repository.list_by_ids([dish.id])[0]
            request = WeeklyMealPlanRequest(
                household_size=2,
                day_count=14,
                weekly_budget_sgd=100,
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
            )
            one = service.grocery_aggregator.estimate([recipe], request, shares=[1]).purchase_total_sgd
            request = request.model_copy(update={"weekly_budget_sgd": (round(one * 100) - cents_short) / 100})

            def run():
                return service.plan_dishes(
                    request,
                    first_day=2,
                    day_count=2,
                    day_indices=[2, 9],
                    rest=[(recipe, 1), (recipe, 1)],
                    rest_days=[1, 8],
                )

            if cents_short:
                with pytest.raises(ProductPlanningError):
                    run()
            else:
                assert len(run()) == 2
                full = service.grocery_aggregator.estimate([recipe] * 4, request, shares=[1] * 4, trips=[1, 1, 2, 2])
                assert full.purchase_total_sgd == 2 * one
                assert full.within_weekly_budget
        finally:
            database.close()
