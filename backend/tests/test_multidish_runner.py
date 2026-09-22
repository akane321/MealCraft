"""Protocol v2-multidish runner: arms answer in the common shape and the scorer reads them."""

import json

from app.core.paths import repository_root
from app.evaluation.multidish_runner import evaluate, rule_constraints

EPISODES = repository_root() / "data/evaluation/dev/v2-multidish/episodes"


def load(episode_id: str) -> dict:
    return json.loads((EPISODES / f"{episode_id}.json").read_text(encoding="utf-8"))


def test_gold_beam_plans_a_composed_week_and_the_rules_ask_for_a_missing_household_size():
    report = evaluate([load("md-dev-001"), load("md-dev-009")], arms=("O1", "C"))
    rows = {(r["episode_id"], r["arm"]): r for r in report["episodes"]}

    assert rows["md-dev-001", "O1"]["strict_success"], rows["md-dev-001", "O1"]["failed"]
    assert rows["md-dev-001", "O1"]["dishes"] == 21  # seven dinners of main, vegetable and the optional soup
    assert rows["md-dev-009", "C"]["answered"] == "clarification" and rows["md-dev-009", "C"]["strict_success"]


def test_the_rule_parser_reads_an_english_allergen_on_top_of_the_profile():
    understood = rule_constraints(
        load("md-dev-010")
        | {"scenario": {**load("md-dev-010")["scenario"], "user_request": "Four of us, one has a shellfish allergy."}}
    )

    assert "shellfish" in understood.allergens and understood.household_size == 4


def test_the_committed_pools_are_the_drawn_ones():
    from app.evaluation.multidish_pool import draw

    for path in sorted(EPISODES.glob("*.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, path.name
        assert episode["scenario"]["fairprice_product_ids"] == products, path.name


def test_every_developer_label_is_proven_from_its_pool():
    from app.evaluation.multidish_labels import check

    for path in sorted(EPISODES.glob("*.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        assert check(episode) is None, (path.name, check(episode))


def test_strong_rules_honour_a_request_and_vary_more_than_the_greedy_floor():
    from app.evaluation.multidish_runner import greedy_selector, strong_rule_selector
    from tests.test_planning_meal_composition import three_days

    asked = three_days(repetition_rules={"recipe_counts": [{"recipe_id": "beef", "min_uses": 2}]})
    strong = strong_rule_selector(asked)
    assert sum(a.recipe_id == "beef" for a in strong.assignments) >= 2

    plain = three_days()
    distinct = lambda solution: len({a.recipe_id for a in solution.assignments})  # noqa: E731
    assert distinct(strong_rule_selector(plain)) > distinct(greedy_selector(plain))
