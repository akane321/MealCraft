import copy
import json
from functools import cache

from app.core.paths import repository_root
from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping, PlanCoverage, map_ingredient
from app.evaluation.baseline_recomputation import line_allergens
from app.evaluation.baseline_resources import load_resources
from app.evaluation.baseline_validation import validate_baseline_plan

EPISODE = repository_root() / "data/evaluation/dev/v2-multidish/episodes/md-dev-001.json"
SLOTS = ("mon-dinner", "tue-dinner", "wed-dinner", "thu-dinner", "fri-dinner", "sat-dinner", "sun-dinner")


@cache
def resources():
    return load_resources()


def line(name: str, grams: float, ingredient_id: str | None) -> IngredientMapping:
    return IngredientMapping(name, grams, ingredient_id, "matched" if ingredient_id else "unmatched")


def week(main_lines, vegetable_lines) -> PlanCoverage:
    dishes = []
    for slot in SLOTS:
        dishes.append(DishCoverage(slot, "main", "Chicken rice", 4, 30, tuple(main_lines)))
        dishes.append(DishCoverage(slot, "vegetable", "Garlic broccoli", 4, 15, tuple(vegetable_lines)))
    return PlanCoverage(tuple(dishes))


def validate(coverage: PlanCoverage, allergens=(), **hard):
    episode = json.loads(EPISODE.read_text(encoding="utf-8"))
    episode = copy.deepcopy(episode)
    episode["gold"]["applicable_hard_constraints"]["allergens_absent"] = list(allergens)
    episode["gold"]["applicable_hard_constraints"].update(hard)
    return validate_baseline_plan(
        episode,
        coverage,
        ingredient_facts=resources().ingredient_facts,
        frozen_products=resources().frozen_products,
    )


MAIN = [line("chicken breast", 600, "chicken_breast"), line("rice", 400, "rice")]
VEGETABLE = [line("broccoli", 500, "broccoli"), line("garlic", 10, "garlic")]


def test_a_fully_mapped_week_goes_through_the_product_validator():
    result = validate(week(MAIN, VEGETABLE))
    assert result.report.purchase_total_sgd > 0  # the validator priced the week on the frozen snapshot
    assert result.strict_passed and result.adjusted_passed
    assert result.unverified == ()


def test_unknown_allergen_status_is_unsafe_only_on_the_strict_basis():
    result = validate(week([*MAIN, line("mystery sauce", 20, None)], VEGETABLE), allergens=["peanut"])
    assert result.strict_passed is False
    assert ("allergen_unknown", "mon-dinner:main:0") in result.unverified
    assert any(code == "unmapped_lines" for code, _ in result.unverified)


def test_a_present_allergen_fails_both_bases():
    result = validate(week([*MAIN, line("peanuts", 30, "peanut")], VEGETABLE), allergens=["peanut"])
    assert any(check.code == "allergen" and check.status == "failed" for check in result.report.checks)
    assert result.strict_passed is False and result.adjusted_passed is False


def test_a_dish_below_the_threshold_is_unverifiable():
    result = validate(week(MAIN, [line("broccoli", 100, "broccoli"), line("odd leaf", 400, None)]))
    assert any(code == "dish_coverage" for code, _ in result.unverified)
    assert result.strict_passed is False


def check(result, code):
    return next(item for item in result.report.checks if item.code == code)


def test_a_passed_budget_with_unmapped_lines_is_indeterminate():
    assert check(validate(week(MAIN, VEGETABLE), budget_sgd=1000), "purchase_budget").status == "passed"
    result = validate(week([*MAIN, line("mystery sauce", 20, None)], VEGETABLE), budget_sgd=1000)
    assert check(result, "purchase_budget").status == "indeterminate"
    assert result.strict_passed is False


def test_a_failed_diet_check_is_indeterminate_not_failed():
    result = validate(week(MAIN, VEGETABLE), dietary_tags_required=["vegetarian"])
    assert check(result, "dietary_requirement").status == "indeterminate"
    assert result.strict_passed is False and result.adjusted_passed is True


def test_a_hierarchy_mapped_soy_milk_keeps_soy():
    # "soy milk" is not in the catalog and maps to milk (dairy only): the keyword scan must still add soy.
    loaded = resources()
    for name in ("soy milk", "unsweetened soy milk"):
        mapping = map_ingredient(
            name, 200, names=loaded.names, aliases=loaded.aliases, matcher=loaded.matcher, parents=loaded.parents
        )
        assert mapping.needs_review
        found, _ = line_allergens(mapping, loaded.ingredient_facts)
        assert "soy" in found, (name, mapping.ingredient_id, found)
