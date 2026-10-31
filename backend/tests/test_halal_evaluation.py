"""Halal in the evaluation (docs/evaluation/halal.md): the baseline and strict scorers and the developer cases."""

import copy
import json

import pytest

from app.core.paths import repository_root
from app.data import halal as halal_data
from app.evaluation import baseline_validation
from app.evaluation.common_output import CommonEpisodeResponse
from app.evaluation.halal_scoring import bought_certified, line_problem
from app.evaluation.multidish_labels import check as proven_label
from app.evaluation.multidish_pool import draw
from app.evaluation.multidish_runner import build_problem, evaluate, gold_constraints, load_episodes, rule_constraints
from app.evaluation.release_catalog import load_release_catalog
from app.evaluation.strict_success import _check_halal
from tests.test_baseline_validation import EPISODE, VEGETABLE, line, resources, week

DEV_SET = repository_root() / "data/evaluation/dev/halal-v1.json"
CERTIFIED_CHICKEN = frozenset({"chicken_breast"})


# --- the line rule, from the committed labels -------------------------------------------------------------------


def test_each_line_is_judged_by_its_label_and_unknown_is_never_halal():
    assert line_problem("rice", ()) is None
    assert line_problem("pork_belly", ()) == "not_halal"
    assert line_problem("sausage", ()) == "uncertain"
    assert line_problem("not_in_any_catalog", ()) == "uncertain"  # no label: unknown
    assert line_problem(None, ()) == "unmapped"


def test_a_meat_line_passes_only_with_a_certified_product():
    assert line_problem("chicken_breast", ()) == "no certified product"
    assert line_problem("chicken_breast", CERTIFIED_CHICKEN) is None
    assert line_problem("pork_belly", CERTIFIED_CHICKEN | {"pork_belly"}) == "not_halal"  # a product never rescues it


def test_a_purchase_is_certified_only_when_every_product_bought_is(monkeypatch):
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {"p-ok": True, "p-no": None})
    shopping = [("chicken_breast", "p-ok"), ("beef", "p-ok"), ("beef", "p-no"), ("lamb", None), ("duck", "unlisted")]
    assert bought_certified(shopping) == {"chicken_breast"}


def test_a_frozen_id_shared_by_two_ingredients_is_certified_by_its_raw_fairprice_id():
    # 13097675 and 13104103 are the certified chicken_breast products; the catalogue freezes 13097675 as
    # "13097675@chicken_breast" because another ingredient shares it.
    assert bought_certified([("chicken_breast", "13097675@chicken_breast")]) == {"chicken_breast"}
    assert bought_certified([("chicken_breast", "fixture:13104103")]) == {"chicken_breast"}
    assert bought_certified([("chicken_breast", "13097675@chicken_breast"), ("chicken_breast", None)]) == frozenset()
    assert halal_data.product_certified("13097675@chicken_breast") is True


def test_the_snapshot_certifies_a_shared_product_by_its_raw_fairprice_id():
    product = (
        resources()
        .frozen_products[0]
        .model_copy(
            update={"ingredient_id": "chicken_breast", "product_id": "13097675@chicken_breast", "halal_certified": None}
        )
    )
    assert baseline_validation.snapshot_certified([product]) == {"chicken_breast"}


# --- the baseline scorer ----------------------------------------------------------------------------------------


def baseline(coverage, *, halal=True, certified=(), monkeypatch=None):
    """The week through the baseline validator; `certified` names the ingredients the snapshot certifies."""
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    episode = copy.deepcopy(json.loads(EPISODE.read_text(encoding="utf-8")))
    episode["gold"]["applicable_hard_constraints"]["halal_required"] = halal
    products = [
        p.model_copy(update={"halal_certified": True if p.ingredient_id in certified else None})
        for p in resources().frozen_products
    ]
    return baseline_validation.validate_baseline_plan(
        episode, coverage, ingredient_facts=resources().ingredient_facts, frozen_products=products
    )


def halal_failures(result):
    return [c for c in result.report.checks if c.code == "halal_requirement" and c.status == "failed"]


def chicken_week(*extra):
    return week([line("chicken breast", 600, "chicken_breast"), line("rice", 400, "rice"), *extra], VEGETABLE)


def test_a_week_of_halal_lines_with_a_certified_meat_product_passes(monkeypatch):
    result = baseline(chicken_week(), certified={"chicken_breast"}, monkeypatch=monkeypatch)
    assert halal_failures(result) == []
    assert result.strict_passed and result.adjusted_passed


def test_a_meat_line_without_a_certified_product_in_the_snapshot_fails_both_bases(monkeypatch):
    result = baseline(chicken_week(), monkeypatch=monkeypatch)
    failed = halal_failures(result)
    assert failed and "chicken breast (no certified product)" in failed[0].detail
    assert result.strict_passed is False and result.adjusted_passed is False


@pytest.mark.parametrize(
    ("extra", "why"),
    [
        (line("bacon bits", 30, "bacon"), "not_halal"),
        (line("pork sausage", 100, "sausage"), "uncertain"),
        (line("mystery sauce", 20, None), "unmapped"),
    ],
)
def test_a_not_halal_uncertain_or_unmapped_line_fails_even_with_certified_meat(extra, why, monkeypatch):
    result = baseline(chicken_week(extra), certified={"chicken_breast"}, monkeypatch=monkeypatch)
    assert any(f"({why})" in check.detail for check in halal_failures(result)), why
    assert result.strict_passed is False and result.adjusted_passed is False


def test_the_same_lines_are_not_judged_for_halal_in_a_household_that_does_not_need_it(monkeypatch):
    result = baseline(chicken_week(line("bacon bits", 30, "bacon")), halal=False, monkeypatch=monkeypatch)
    assert halal_failures(result) == []


# --- the strict scorer ------------------------------------------------------------------------------------------


def recipe(slug, *ingredients, quantity=100):
    return {
        "slug": slug,
        "ingredients": [{"ingredient": name, "quantity": quantity, "unit": "g"} for name in ingredients],
    }


def answer(*shopping):
    return CommonEpisodeResponse.model_validate(
        {
            "episode_id": "e",
            "system_id": "s",
            "status": "plan",
            "plan": {
                "assignments": [],
                "shopping": [{"ingredient_id": i, "product_id": p, "packages": 1} for i, p in shopping],
            },
        }
    )


def test_the_strict_scorer_fails_pork_unknown_and_uncertified_meat(monkeypatch):
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {"p-ok": True})
    bought = answer(("chicken_breast", "p-ok"), ("beef", "p-other"), ("rice", None))
    assert _check_halal([recipe("veg", "rice", "broccoli")], bought).outcome == "passed"
    assert _check_halal([recipe("certified", "rice", "chicken_breast")], bought).outcome == "passed"
    for bad in (recipe("pork", "rice", "pork_belly"), recipe("unknown", "rice", "sausage")):
        assert _check_halal([bad], bought).outcome == "failed", bad["slug"]
    uncertified = _check_halal([recipe("beef-dish", "rice", "beef")], bought)
    assert uncertified.outcome == "failed" and "beef" in uncertified.detail
    assert _check_halal([recipe("unlisted", "rice", "duck")], bought).outcome == "failed"  # never bought as certified


def test_a_zero_gram_meat_line_needs_no_purchase_but_a_zero_gram_pork_line_still_counts(monkeypatch):
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    nothing = answer()
    assert _check_halal([recipe("trace", "rice", "chicken_breast", quantity=0)], nothing).outcome == "passed"
    assert _check_halal([recipe("pork", "rice", "pork_belly", quantity=0)], nothing).outcome == "failed"


# --- the developer cases ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def episodes():
    return load_episodes(DEV_SET)[1]


def test_the_developer_set_has_the_four_halal_cases_and_is_not_held_out(episodes):
    assert [e["episode_id"] for e in episodes] == [f"halal-dev-00{n}" for n in (1, 2, 3, 4)]
    assert all(e["gold"]["applicable_hard_constraints"]["halal_required"] for e in episodes)
    assert any(e["language"] == "zh" for e in episodes)
    assert any(e["scenario"]["household_profile"]["household_size"] == 5 for e in episodes)
    assert "heldout" not in DEV_SET.parts and "sealed" not in str(DEV_SET)


def test_the_pools_are_the_drawn_ones_and_every_label_is_proven(episodes):
    for episode in episodes:
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, episode["episode_id"]
        assert episode["scenario"]["fairprice_product_ids"] == products, episode["episode_id"]
        assert proven_label(episode) is None, (episode["episode_id"], proven_label(episode))


def test_each_pool_holds_the_dish_that_case_is_about(episodes):
    from app.data.halal import recipe_halal_status

    by_slug = load_release_catalog().by_slug
    status = {
        e["episode_id"]: {
            recipe_halal_status([line["ingredient"] for line in by_slug[slug]["ingredients"]])
            for slug in e["scenario"]["recipe_candidate_slugs"]
        }
        for e in episodes
    }
    assert {"needs_certification", "not_halal"} <= status["halal-dev-001"]  # pork-free meat, and pork
    assert "uncertain" in status["halal-dev-002"]  # a line of unknown status


def test_the_chinese_request_alone_carries_the_halal_requirement(episodes):
    chinese = next(e for e in episodes if e["language"] == "zh")
    assert "requires_halal" not in chinese["scenario"]["household_profile"]
    assert gold_constraints(chinese).requires_halal and rule_constraints(chinese).requires_halal


def test_the_problem_a_halal_episode_builds_carries_the_switch_the_statuses_and_the_certified_products(episodes):
    problem = build_problem(episodes[0], gold_constraints(episodes[0]))
    assert problem.requires_halal
    assert {r.halal_status for r in problem.recipes} <= {"halal", "needs_certification", "not_halal", "uncertain"}
    assert None not in {r.halal_status for r in problem.recipes}
    assert any(p.halal_certified for p in problem.products)  # the offline facts reach the planner


def test_the_rule_arms_plan_every_halal_case_and_the_scorer_accepts_the_plans(episodes):
    report = evaluate(episodes, arms=("O1", "C", "F"))
    assert all(row["strict_success"] for row in report["episodes"]), [
        (r["episode_id"], r["arm"], r["failed"]) for r in report["episodes"] if not r["strict_success"]
    ]
