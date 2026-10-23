from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping, PlanCoverage
from app.evaluation.baseline_verification import verify_coverage


def line(name: str, grams: float, ingredient_id: str | None, status: str = "matched") -> IngredientMapping:
    return IngredientMapping(name, grams, ingredient_id, status, needs_review=status == "needs_review")


def dish(name: str, *mappings: IngredientMapping) -> DishCoverage:
    return DishCoverage("mon-dinner", None, name, 2, 30, mappings)


def test_threshold_is_per_dish_not_per_plan():
    # 94% of the plan's grams map, but the small dish maps only half of its own.
    plan = PlanCoverage(
        (
            dish("big", line("rice", 850, "rice")),
            dish("small", line("tofu", 50, "tofu"), line("mystery", 50, None, "unmatched")),
            dish("edge", line("egg", 90, "egg"), line("odd", 10, None, "unmatched")),
        )
    )
    result = verify_coverage(plan)
    assert [item.verifiable for item in result.dishes] == [True, False, True]
    assert result.gram_coverage == 990 / 1050
    assert result.verifiable_dish_share == 2 / 3
    assert result.all_dishes_verifiable is False  # the strict basis
    assert result.unmatched_count == 2


def test_flagged_lines_go_to_the_review_list():
    plan = PlanCoverage((dish("d", line("rice", 100, "rice"), line("cilantro", 10, "coriander", "needs_review")),))
    result = verify_coverage(plan)
    assert result.all_dishes_verifiable is True
    assert result.needs_review_count == 1
    assert [item.original_name for item in result.review_list] == ["cilantro"]


def test_empty_plan_is_not_verifiable():
    result = verify_coverage(PlanCoverage(()))
    assert result.all_dishes_verifiable is False
    assert result.verifiable_dish_share is None
