"""Protocol v3-meal-day-week: drawn pools, proven labels, and the product path scored."""

import copy
import json

from app.core.paths import repository_root
from app.evaluation.meal_day_week_runner import evaluate, run_episode, scorer_catalogs, v3_checks
from app.evaluation.multidish_labels import check, slot_roles
from app.evaluation.multidish_pool import draw

EPISODES = repository_root() / "data/evaluation/dev/v3-meal-day-week/episodes"


def load(episode_id: str) -> dict:
    return json.loads((EPISODES / f"{episode_id}.json").read_text(encoding="utf-8"))


def test_the_committed_pools_are_the_drawn_ones_and_every_label_is_proven():
    paths = sorted(EPISODES.glob("*.json"))
    assert len(paths) >= 12
    for path in paths:
        episode = json.loads(path.read_text(encoding="utf-8"))
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, path.name
        assert episode["scenario"]["fairprice_product_ids"] == products, path.name
        assert check(episode) is None, (path.name, check(episode))


def test_a_shape_change_applies_to_its_days_and_meal_only():
    soup_on_friday = load("mdw-dev-015")
    before, after = slot_roles(soup_on_friday), slot_roles(soup_on_friday, after_change=True)
    assert list(before) == list(after) and len(after) == 7
    assert [r["role_id"] for r in after["fri-dinner"]] == ["main", "vegetable", "soup"]
    assert all(before[slot] == after[slot] for slot in after if slot != "fri-dinner")

    no_breakfast = slot_roles(load("mdw-dev-014"), after_change=True)
    assert list(no_breakfast) == [f"{day}-dinner" for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]


def test_a_label_names_the_slots_a_change_touches():
    episode = load("mdw-dev-015")
    episode["gold"]["replan_invariants"]["changed_slots"] = ["thu-dinner"]
    assert "changed_slots should be" in check(episode)


def test_the_product_adds_a_soup_to_one_dinner_and_keeps_the_rest():
    episode = load("mdw-dev-015")
    report = evaluate([episode])
    row = report["episodes"][0]
    assert row["strict_success"], row["details"]
    assert row["dishes"] == 15  # seven dinners of two dishes, Friday's with a soup

    # The v3 checks catch a week where another meal moved.
    response, extra = run_episode(episode)
    moved = copy.deepcopy(extra)
    moved["before"]["mon-dinner"] = {"main": "RCP2_NOT_THIS_ONE"}
    codes = {c.code: c.outcome for c in v3_checks(episode, response, moved, scorer_catalogs(episode))}
    assert codes == {"shape_request_understood": "passed", "unchanged_meals_identical": "failed"}
