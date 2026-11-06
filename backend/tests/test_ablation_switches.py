"""Issue #397: each EVALUATION_ABLATION switch changes what the product plans, and only outside production.

Weeks come from development episodes (the product's own in-memory planning of a drawn pool) or the curated
test catalog; no model is called and nothing is priced live.
"""

import json
from collections import Counter

import pytest

from app.agent.parser import FallbackConstraintParser, RuleBasedConstraintParser
from app.api.routes.agent import create_constraint_parser
from app.api.routes.meal_plans import build_meal_plan_service
from app.core.config import ABLATIONS, Settings, ablated, get_settings
from app.core.paths import repository_root
from app.evaluation.meal_day_week_runner import HOUSEHOLD, plan_request, product_database
from app.planning.retailers import fairprice_only
from app.planning.weekly_planner import WeeklyPlanSelectionError
from tests.test_planning_product_path import REQUEST, latest_trace
from tests.test_recipes import recipe_client as recipe_client

EPISODES = repository_root() / "data/evaluation/dev/v3-meal-day-week/episodes"
PLANNING_SWITCHES = (
    "retrieval_off",
    "independent_validator_off",
    "repair_off",
    "diversity_off",
    "local_improvement_off",
)


@pytest.fixture
def switch(monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "test")
    return lambda name: monkeypatch.setattr(get_settings(), "evaluation_ablation", name)


def episode(episode_id: str) -> dict:
    return json.loads((EPISODES / f"{episode_id}.json").read_text(encoding="utf-8"))


def week(episode_id: str, *, cheapest=False, budget=None):
    """The episode's week as (day, meal, role, recipe) rows, or "refused"; with `cheapest` the cheapest week's total.

    `budget` replaces the episode's weekly budget."""
    drawn = episode(episode_id)
    request = plan_request(drawn)
    if budget is not None:
        request = request.model_copy(update={"weekly_budget_sgd": budget})
    with fairprice_only(), product_database(drawn) as factory, factory() as session:
        plans = build_meal_plan_service(session, HOUSEHOLD)
        if cheapest:
            return plans.cheapest_week(request)
        try:
            plan = plans.generate(request)
        except WeeklyPlanSelectionError:
            return "refused"
        return tuple(sorted((d.day_index, d.meal_type, d.role_id, d.recipe.slug) for d in plan.days))


def repository_catalog(recipe_client):
    """The repository's curated catalog in the test client's database (as the product-path budget tests use)."""
    from app.data.catalog import import_catalog, load_catalog
    from tests.test_planning_product_path import database

    root = repository_root()
    with database() as session:
        import_catalog(
            session, load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
        )


@pytest.mark.parametrize("environment", ["production", "staging", "development", "test", "Test"])
def test_a_switch_is_read_only_in_development_and_test(monkeypatch, environment):
    monkeypatch.setattr(get_settings(), "environment", environment)
    for name in ABLATIONS:
        monkeypatch.setattr(get_settings(), "evaluation_ablation", name)
        on = environment.casefold() in {"development", "test"}
        assert {other: ablated(other) for other in ABLATIONS} == {other: on and other == name for other in ABLATIONS}
    monkeypatch.setattr(get_settings(), "evaluation_ablation", None)
    assert not any(ablated(name) for name in ABLATIONS)


@pytest.mark.parametrize(
    ("name", "episode_id"),
    [
        ("retrieval_off", "mdw-dev-001"),
        ("diversity_off", "mdw-dev-001"),
        # v3 repair (#426, 2026-11-06): on mdw-dev-007 the switch no longer changes the week; it does on 008.
        ("local_improvement_off", "mdw-dev-008"),
        ("independent_validator_off", "mdw-dev-009"),  # refused by the budget check by default
    ],
)
def test_a_planning_switch_changes_a_development_week(switch, name, episode_id):
    switch(None)
    default = week(episode_id)
    switch(name)
    assert week(episode_id) != default


def test_the_planning_switches_plan_five_different_weeks(switch):
    weeks = {}
    for name in PLANNING_SWITCHES:
        switch(name)
        weeks[name] = week("mdw-dev-007")
    # v3 repair (#426, re-measured 2026-11-06 on all 21 development episodes): no episode plans five different weeks
    # any more. On mdw-dev-007 four switches plan four different weeks and repair_off is refused (without repair the
    # validator's refusal stands), which is still a different outcome; only that one may be refused.
    assert [name for name, outcome in weeks.items() if outcome == "refused"] == ["repair_off"]
    assert len(set(weeks.values())) == len(PLANNING_SWITCHES), weeks.keys()


def test_retrieval_off_recalls_candidates_by_id_not_relevance(switch):
    drawn = episode("mdw-dev-001")
    orders = {}
    for name in (None, "retrieval_off"):
        switch(name)
        with fairprice_only(), product_database(drawn) as factory, factory() as session:
            service = build_meal_plan_service(session, HOUSEHOLD).recommendation_service
            orders[name] = [r.recipe.id for r in service.recommend(plan_request(drawn)).recommendations]
    assert sorted(orders[None]) == orders["retrieval_off"] != orders[None]


def test_repair_off_drops_the_cost_led_fallback_search(recipe_client, switch):
    repository_catalog(recipe_client)
    body = {"requires_halal": False, **REQUEST, "weekly_budget_sgd": 60}
    answers = {}
    for name in (None, "repair_off", "retrieval_off"):
        switch(name)
        answers[name] = recipe_client.post("/api/plans/generate", json=body)
        _, trace = latest_trace()
        assert ("cost_fallback" in trace) == (name != "repair_off")
    assert answers[None].status_code == 201, answers[None].text
    assert answers["repair_off"].status_code == 422
    assert answers["retrieval_off"].status_code == 201  # a different switch from repair_off


def test_repair_off_drops_the_second_attempt_with_the_wider_pool(recipe_client, switch):
    body = {"requires_halal": False, **REQUEST, "max_cooking_time_minutes": 30, "weekly_budget_sgd": 0.01}
    for name in (None, "repair_off"):
        switch(name)
        assert recipe_client.post("/api/plans/generate", json=body).status_code == 422
        _, trace = latest_trace()
        assert ("prior_candidate_attempt" in trace) == (name is None)


def test_repair_off_drops_the_composed_weeks_last_resort_cheapest_search(switch):
    """Under S$25 every week of mdw-dev-013's main-and-vegetable search fails the budget; by default the cheapest-week
    search then runs and its checked weeks (S$25.59 and up) are what the refusal offers. Without repair nothing does."""
    drawn = episode("mdw-dev-013")
    request = plan_request(drawn).model_copy(update={"weekly_budget_sgd": 25.0})
    attempts = {}
    for name in (None, "repair_off"):
        switch(name)
        with fairprice_only(), product_database(drawn) as factory, factory() as session:
            error = build_meal_plan_service(session, HOUSEHOLD).check(request)
        assert error is not None
        attempts[name] = error.trace["validation_attempts"]
    assert attempts[None] and all(attempt.get("cheapest_search") for attempt in attempts[None])
    assert min(attempt["purchase_total_sgd"] for attempt in attempts[None]) > 25
    assert attempts["repair_off"] == []


def test_repair_off_keeps_the_cheapest_week_search(switch):
    switch(None)
    default = week("mdw-dev-001", cheapest=True)
    switch("repair_off")
    assert week("mdw-dev-001", cheapest=True) == default > 0


@pytest.mark.parametrize(("episode_id", "budget"), [("mdw-dev-001", None), ("mdw-dev-008", 60.0)])
def test_diversity_off_keeps_optional_dishes_filled(switch, episode_id, budget):
    switch(None)
    default = week(episode_id, budget=budget)
    switch("diversity_off")
    plain = week(episode_id, budget=budget)
    assert plain != default
    if budget is None:
        assert len({row[3] for row in plain}) < len({row[3] for row in default})
    # Empty optional dishes are completeness, not variety: every role is filled as often as by default
    # (at S$60 mdw-dev-008 leaves a vegetable out when the order forgets them).
    assert Counter(row[1:3] for row in plain) == Counter(row[1:3] for row in default)


def test_diversity_off_lets_a_dish_follow_itself(switch):
    """The meal beam's adjacent-repeat cost is part of the variety term too: a dinner-only main and vegetable week."""

    def adjacent(rows) -> int:
        dinners = {}
        for day, meal, _, recipe in rows:
            dinners.setdefault((day, meal), set()).add(recipe)
        ordered = [dinners[key] for key in sorted(dinners)]
        return sum(len(one & other) for one, other in zip(ordered, ordered[1:], strict=False))

    switch(None)
    default = week("mdw-dev-013")
    switch("diversity_off")
    plain = week("mdw-dev-013")
    assert adjacent(default) == 0 and len({row[3] for row in default}) == 14
    # With the adjacent cost still on, the week alternated four dishes and never repeated the night before.
    assert adjacent(plain) > 0 and len({row[3] for row in plain}) < 4


def test_diversity_off_keeps_the_households_cap_on_uses(switch):
    switch("diversity_off")
    # The household's own cap of one use per dish is a hard rule (mdw-dev-012 states it).
    assert max(Counter(row[3] for row in week("mdw-dev-012")).values()) == 1


def test_local_improvement_off_skips_the_annealing_step(recipe_client, switch):
    for name in (None, "local_improvement_off"):
        switch(name)
        response = recipe_client.post("/api/plans/generate", json={"requires_halal": False, **REQUEST})
        assert response.status_code == 201, response.text
        _, trace = latest_trace()
        assert ("local_improvement" in trace) == (name is None)


def test_independent_validator_off_passes_a_week_the_extra_per_meal_check_fails(recipe_client, monkeypatch, switch):
    from app.services.recommendation import RecipeRecommendationService

    original = RecipeRecommendationService.recommend

    def faulty_admission(self, constraints, **kwargs):
        return original(self, constraints.model_copy(update={"budget_per_meal_sgd": None}), **kwargs)

    monkeypatch.setattr(RecipeRecommendationService, "recommend", faulty_admission)
    body = {"requires_halal": False, **REQUEST, "budget_per_meal_sgd": 0.01}
    switch(None)
    assert recipe_client.post("/api/plans/generate", json=body).status_code == 422
    switch("independent_validator_off")
    response = recipe_client.post("/api/plans/generate", json=body)
    assert response.status_code == 201, response.text
    run, trace = latest_trace()
    assert run.status == "succeeded"
    assert trace["validation"]["status"] == "passed"
    # The checks stay for the scorer, failures and all.
    assert any(c["code"] == "per_meal_budget" and c["status"] == "failed" for c in trace["validation"]["checks"])
    assert recipe_client.get(f"/api/plans/{response.json()['id']}").json() == response.json()


def test_rule_only_parser_overrides_the_openai_setting(switch):
    settings = Settings(agent_parser_provider="openai", openai_api_key="sk-test-not-a-key")
    switch(None)
    default = create_constraint_parser(settings)
    assert isinstance(default, FallbackConstraintParser)
    assert default.scope_classifier is not None
    switch("rule_only_parser")
    assert type(create_constraint_parser(settings)) is RuleBasedConstraintParser
