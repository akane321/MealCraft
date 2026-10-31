"""Halal in the evaluation (docs/evaluation/halal.md): the baseline and strict scorers and the developer cases."""

import copy
import json

import pytest

from app.core.paths import repository_root
from app.data import halal as halal_data
from app.evaluation import baseline_validation, multidish_labels
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
    assert line_problem("sausage", ()) == "no certified product"  # owner 10-31: only as a marked product
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
    """The week through the baseline validator; `certified` names the ingredients (or single products) the snapshot
    certifies."""
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    episode = copy.deepcopy(json.loads(EPISODE.read_text(encoding="utf-8")))
    episode["gold"]["applicable_hard_constraints"]["halal_required"] = halal
    products = [
        p.model_copy(update={"halal_certified": True if {p.ingredient_id, p.product_id} & set(certified) else None})
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
        (line("pork sausage", 100, "sausage"), "no certified product"),
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


# --- a pantry basic that needs certification (owner, 2026-10-31) ----------------------------------------------


def needing_certification(names):
    return {name for name in names if halal_data.needs_certification(name)}


def test_a_halal_baseline_does_not_take_a_basic_that_needs_certification_as_at_home():
    loaded = resources()
    plain, halal = loaded.not_bought({}), loaded.not_bought({}, halal=True)
    assert {"soy_sauce", "vinegar", "mayo", "ketchup"} <= plain
    assert not {"soy_sauce", "vinegar", "mayo", "ketchup"} & halal  # bought, as a certified product
    assert {"rice", "flour", "water", "ice"} <= halal  # the other basics stay at home
    assert plain - halal == needing_certification(loaded.basic_seasonings)
    assert loaded.not_bought({"requires_halal": True}) == halal
    assert loaded.not_bought({"missing_basics": ["rice"]}, halal=True) == halal - {"rice"}


def soy_week():
    return chicken_week(line("soy sauce", 30, "soy_sauce"))


def test_a_basic_that_needs_certification_fails_a_halal_baseline_without_a_certified_product(monkeypatch):
    result = baseline(soy_week(), certified={"chicken_breast"}, monkeypatch=monkeypatch)
    failed = halal_failures(result)
    assert failed and "soy sauce (no certified product)" in failed[0].detail
    assert result.strict_passed is False and result.adjusted_passed is False


def test_a_basic_that_needs_certification_passes_with_a_certified_product_and_is_priced_from_it(monkeypatch):
    result = baseline(soy_week(), certified={"chicken_breast", "soy_sauce"}, monkeypatch=monkeypatch)
    assert halal_failures(result) == []
    assert result.strict_passed and result.adjusted_passed
    # Only the dearest soy sauce (114695, S$6.31) certified: the week is priced from it, not from a cheaper one.
    dearest = baseline(soy_week(), certified={"chicken_breast", "114695"}, monkeypatch=monkeypatch)
    assert halal_failures(dearest) == []
    assert dearest.report.purchase_total_sgd > result.report.purchase_total_sgd


def test_the_same_basic_is_not_judged_for_halal_in_a_household_that_does_not_need_it(monkeypatch):
    result = baseline(soy_week(), halal=False, monkeypatch=monkeypatch)
    assert halal_failures(result) == []


def test_the_strict_scorer_fails_a_basic_that_needs_certification_unless_it_is_bought_certified(monkeypatch):
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {"p-ok": True})
    dish = [recipe("stir-fry", "rice", "soy_sauce")]
    assumed_at_home = _check_halal(dish, answer(("rice", None)))
    assert assumed_at_home.outcome == "failed" and "soy_sauce" in assumed_at_home.detail
    assert _check_halal(dish, answer(("soy_sauce", "p-other"))).outcome == "failed"  # not a certified product
    assert _check_halal(dish, answer(("soy_sauce", "p-ok"))).outcome == "passed"
    assert _check_halal([recipe("plain", "rice", "soy_sauce", quantity=0)], answer()).outcome == "passed"


def soy_episode(episode, *, halal):
    soy = [p["external_id"] for p in load_release_catalog().products if p["ingredient_id"] == "soy_sauce"]
    gold = {**episode["gold"]["applicable_hard_constraints"], "halal_required": halal}
    gold |= {"allergens_absent": [], "excluded_ingredients_absent": [], "dietary_tags_required": []}
    return {
        **episode,
        "gold": {**episode["gold"], "applicable_hard_constraints": gold},
        "scenario": {**episode["scenario"], "fairprice_product_ids": soy},
    }


def test_the_label_proofs_let_a_halal_case_use_a_basic_that_needs_certification_only_with_a_certified_product(
    monkeypatch, episodes
):
    stir_fry = {
        "slug": "s",
        "title": "s",
        "dietary_tags": [],
        "ingredients": [{"ingredient": "soy_sauce", "quantity": 10}],
    }
    certified = {"12602826"}  # a FairPrice soy sauce marked Halal
    monkeypatch.setattr(multidish_labels, "product_certified", lambda product_id: product_id in certified)
    assert multidish_labels._context(soy_episode(episodes[0], halal=True))[2](stir_fry)
    certified.clear()
    assert not multidish_labels._context(soy_episode(episodes[0], halal=True))[2](stir_fry)
    assert multidish_labels._context(soy_episode(episodes[0], halal=False))[2](stir_fry)  # not halal: unchanged


def test_the_week_proofs_price_a_basic_that_needs_certification_from_certified_products_only(monkeypatch):
    plain = multidish_labels.bought("soy_sauce", 100)
    assert multidish_labels.bought("soy_sauce", 100, halal=True) < float("inf")  # a certified product exists
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    assert multidish_labels.bought("soy_sauce", 100) == plain
    assert multidish_labels.bought("soy_sauce", 100, halal=True) == float("inf")


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
    from app.data.halal import halal_labels, needs_certification, product_certified, recipe_halal_status

    by_slug = load_release_catalog().by_slug
    status = {
        e["episode_id"]: {
            recipe_halal_status([line["ingredient"] for line in by_slug[slug]["ingredients"]])
            for slug in e["scenario"]["recipe_candidate_slugs"]
        }
        for e in episodes
    }
    assert {"needs_certification", "not_halal"} <= status["halal-dev-001"]  # pork-free meat, and pork
    # A line of unknown status: since 10-31 one that needs a marked product the pool's snapshot does not have.
    certified = {
        row["ingredient_id"]
        for row in load_release_catalog().products
        if row["external_id"]
        in set(next(e for e in episodes if e["episode_id"] == "halal-dev-002")["scenario"]["fairprice_product_ids"])
        and product_certified(row["external_id"])
    }
    dev_002 = next(e for e in episodes if e["episode_id"] == "halal-dev-002")
    labels = halal_labels()
    assert any(
        needs_certification(line["ingredient"])
        and labels[line["ingredient"]]["source"] == "human"  # a sauce or basic, not meat
        and line["ingredient"] not in certified
        for slug in dev_002["scenario"]["recipe_candidate_slugs"]
        for line in by_slug[slug]["ingredients"]
    )


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


def test_a_halal_case_recomputes_a_baseline_only_on_what_it_may_buy(monkeypatch):
    """The recomputed baseline price of a halal case uses the same certified-only products as its validation."""
    from app.evaluation.baseline_validation import halal_purchasable

    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    products = [
        p.model_copy(update={"halal_certified": True if p.product_id == "114695" else None})
        for p in resources().frozen_products
        if p.ingredient_id in {"soy_sauce", "rice"}
    ]
    kept = {p.product_id for p in halal_purchasable(products)}
    assert {p.product_id for p in products if p.ingredient_id == "soy_sauce"} & kept == {"114695"}
    assert {p.product_id for p in products if p.ingredient_id == "rice"} <= kept
