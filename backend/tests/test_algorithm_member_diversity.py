import pytest

from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.schemas.planning_v2 import PlanningAssignment, PlanningSlotMember
from tests.test_algorithm_price_priority import packet


def family(size):
    problem, objective = packet()
    members = [
        PlanningSlotMember(name=f"adult-{i}", servings=1, dietary_requirements=["vegetarian"] if i == 0 else [])
        for i in range(size)
    ]
    for recipe in problem.recipes[:2]:
        recipe.dietary_tags = ["vegetarian"]
    for slot in problem.slots:
        slot.members = members
        slot.servings = size
    if size == 2:
        # The vegetarian adult is away for dinner one; the other adult may eat meat.
        problem.slots[0].members = members[1:]
        problem.slots[0].servings = 1
    problem.purchase_budget_sgd = 100
    return problem, objective


def shared_family():
    from app.schemas.planning_v2 import PlanningMealRole

    problem, objective = family(2)
    for slot in problem.slots:
        slot.members = problem.slots[-1].members
        slot.servings = 2
        slot.composition = [
            PlanningMealRole(role_id=role, courses=["main"], required=True) for role in ("main", "extra")
        ]
    return problem, objective


def test_members_only_count_the_dishes_they_can_eat():
    problem, objective = family(2)
    problem.slots[0].members = problem.slots[1].members
    dishes = [PlanningAssignment(slot_id="s0", recipe_id="a"), PlanningAssignment(slot_id="s1", recipe_id="c")]
    metrics = objective.diversity(problem, dishes)
    assert metrics["table_kinds"] == 2
    assert metrics["member_kinds"] == {"adult-0": 1, "adult-1": 2}
    assert metrics["member_mean"] == 1.5
    assert metrics["member_min"] == 1


def test_absence_and_near_duplicates_do_not_inflate_counts():
    problem, objective = family(2)
    dishes = [PlanningAssignment(slot_id="s0", recipe_id="a"), PlanningAssignment(slot_id="s1", recipe_id="b")]
    metrics = objective.diversity(problem, dishes)
    assert metrics["member_kinds"] == {"adult-0": 1, "adult-1": 1}
    assert metrics["table_kinds"] == 1
    empty = objective.diversity(problem, [])
    assert empty["member_min"] is None
    assert empty["member_mean"] is None
    assert empty["member_kinds"] == {}


def test_member_primary_score_and_table_minimum_are_separate():
    from types import SimpleNamespace

    from app.planning.algorithm_reference import evaluate

    problem, objective = family(2)
    dishes = [PlanningAssignment(slot_id="s0", recipe_id="c"), PlanningAssignment(slot_id="s1", recipe_id="a")]
    assert objective.terms(problem, dishes, SimpleNamespace(checks=[], purchase_total_sgd=4))[1] == -1.5
    score, _, _, report = evaluate(
        objective_planner := SharedScoreCpSat(objective),
        problem,
        (("s0", ((None, "c"),)), ("s1", ((None, "a"),))),
        min_dish_kinds=2,
    )
    assert report.status == "passed"
    assert score is not None
    assert objective_planner.objective.diversity(problem, dishes)["table_kinds"] == 2


def test_missing_member_data_stays_table_only():
    problem, objective = packet()
    metrics = objective.diversity(problem, [])
    assert metrics["member_mean"] is None
    assert metrics["member_min"] is None
    assert metrics["primary_basis"] == "table"


def test_member_only_at_empty_meal_is_not_in_denominator():
    problem, objective = family(2)
    problem.slots[0].members = [PlanningSlotMember(name="guest", servings=1)]
    metrics = objective.diversity(problem, [PlanningAssignment(slot_id="s1", recipe_id="a")])
    assert metrics["member_kinds"] == {"adult-0": 1, "adult-1": 1}
    assert metrics["member_mean"] == metrics["member_min"] == 1


def test_filled_meal_still_counts_ineligible_and_exempt_role_members():
    problem, objective = family(2)
    assignments = [PlanningAssignment(slot_id="s1", recipe_id="c")]
    assert objective.diversity(problem, assignments)["member_kinds"] == {"adult-0": 0, "adult-1": 1}
    problem.uncounted_roles = ["staple"]
    assignments[0].role_id = "staple"
    metrics = objective.diversity(problem, assignments)
    assert metrics["member_kinds"] == {"adult-0": 0, "adult-1": 0}
    assert metrics["member_mean"] == 0


@pytest.mark.parametrize("priority", ["variety", "price"])
def test_optional_meal_member_denominator_matches_exact_models(priority):
    from tests.test_algorithm_price_priority import price_objective

    problem, objective = family(2)
    problem.slots[0].required = False
    problem.slots[0].members = [PlanningSlotMember(name="guest", servings=1, dietary_requirements=["vegan"])]
    if priority == "price":
        objective = price_objective(objective)
    exact = EnumeratedReference(objective).solve_reference(problem)
    for engine in (SharedScoreCpSat, NativeSharedScoreCpSat):
        result = engine(objective).solve_exact(problem)
        assert result["status"].startswith("optimal_for_")
        assert result["score"] == exact["score"]
        assert result["diversity"] == exact["diversity"]
        assert "guest" not in result["diversity"]["member_kinds"]


@pytest.mark.parametrize("size", [2, 6])
def test_family_exact_references_agree_and_report_members(size):
    problem, objective = family(size)
    expected = EnumeratedReference(objective).solve_reference(problem)
    for engine in (SharedScoreCpSat, NativeSharedScoreCpSat):
        result = engine(objective).solve_exact(problem)
        assert result["status"].startswith("optimal_for_")
        assert result["score"] == expected["score"]
        assert result["diversity"] == expected["diversity"]
        assert len(result["diversity"]["member_kinds"]) == size


@pytest.mark.parametrize("size", [2, 6])
@pytest.mark.parametrize(
    "engine",
    [DiversityAwareGreedyPlanner, SharedObjectiveBeamPlanner, GraspPlanner, LocalSearchPlanner, AnnealingPlanner],
)
def test_family_heuristics_pass_independent_validation(size, engine):
    problem, objective = family(size)
    result = engine(objective).solve(problem)
    assert result.status == "feasible"
    assert result.validation.status == "passed"
    metrics = objective.diversity(problem, result.assignments)
    assert metrics["member_min"] >= 1
    assert len(metrics["member_kinds"]) == size


def test_shared_dishes_preserve_member_counts_across_exact_models():
    problem, objective = shared_family()
    expected = EnumeratedReference(objective).solve_reference(problem)
    assert expected["status"] == "optimal_for_generated_options"
    for engine in (SharedScoreCpSat, NativeSharedScoreCpSat):
        actual = engine(objective).solve_exact(problem)
        assert actual["status"].startswith("optimal_for_")
        assert actual["score"] == expected["score"]
        assert actual["diversity"] == expected["diversity"]
