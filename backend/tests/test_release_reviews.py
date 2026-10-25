"""The in-person sampled reviews of a release: the allergen review (03 plan 2.5) and the 100-recipe manual check
(2.7)."""

import importlib.util
import json

import pytest

from app.core.paths import repository_root

SCRIPTS = repository_root() / "data-engineering/scripts"
pytestmark = pytest.mark.skipif(
    not (SCRIPTS / "allergen_review.py").is_file(),
    reason="Repository-only review scripts are not shipped in the backend image.",
)


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


allergens = script("allergen_review") if (SCRIPTS / "allergen_review.py").is_file() else None
manual = script("manual_check") if (SCRIPTS / "manual_check.py").is_file() else None
sampling = script("review_sampling") if (SCRIPTS / "review_sampling.py").is_file() else None


def test_allocation_gives_every_stratum_its_minimum_and_the_rest_by_size() -> None:
    plan = sampling.allocate({"rare": 2, "small": 10, "large": 1000}, 20, 3)
    assert plan == {"rare": 2, "small": 3, "large": 15}
    assert sum(sampling.allocate({"a": 7, "b": 7, "c": 7}, 10, 3).values()) == 10


def test_wilson_interval() -> None:
    assert sampling.wilson(0, 0) is None
    low, high = sampling.wilson(95, 100)
    assert low < 0.95 < high
    assert sampling.wilson(10, 10)[1] == 1.0


@pytest.mark.parametrize("review", ["allergen", "manual"])
def test_the_committed_samples_are_the_draws_of_the_release(review: str) -> None:
    module = allergens if review == "allergen" else manual
    version, recipes = sampling.release_recipes()
    committed = json.loads((module.OUT / "sample.json").read_text(encoding="utf-8"))
    assert module.draw(version, recipes) == committed
    assert committed["size"] == module.SIZE


def test_every_allergen_kind_is_a_stratum_of_its_rarest_allergen() -> None:
    recipes = [
        {"recipe_id": f"R{i:03}", "allergens": allergen}
        for i, allergen in enumerate([["milk"]] * 60 + [["milk", "sesame"]] * 5 + [[]] * 40)
    ]
    sample = allergens.draw("v", recipes)
    assert sample["strata"] == {
        "milk": {"recipes": 60, "drawn": 27},
        "none": {"recipes": 40, "drawn": 19},
        "sesame": {"recipes": 5, "drawn": 4},
    }
    assert allergens.draw("v", recipes) == sample


def _allergen_sample() -> tuple[dict, dict]:
    sample = {
        "release": "v",
        "seed": 1,
        "size": 4,
        "recipes_in_release": 100,
        "strata": {"milk": {"recipes": 90, "drawn": 2}, "none": {"recipes": 10, "drawn": 2}},
        "recipes": [
            {"id": "A", "stratum": "milk", "allergens": ["milk"]},
            {"id": "B", "stratum": "milk", "allergens": ["milk"]},
            {"id": "C", "stratum": "none", "allergens": []},
            {"id": "D", "stratum": "none", "allergens": []},
        ],
    }
    ai = {key: {"allergens": ["milk"] if key in "AB" else ["gluten"], "note": None} for key in "ABCD"}
    return sample, ai


def _row(key: str, confirmed, *, checked: bool = True, note: str | None = None) -> dict:
    return {"id": key, "title": key, "confirmed": confirmed, "note": note, "checked": checked}


def test_allergen_agreement_weights_strata_and_classifies_errors() -> None:
    sample, ai = _allergen_sample()
    rows = [_row("A", "milk"), _row("B", "milk, eggs"), _row("C", "gluten", note="flour"), _row("D", "[]")]
    result = allergens.score(rows, sample, ai)
    assert (result["checked"], result["agree"]) == (4, 2)
    assert result["strata"]["milk"]["agreement"] == 0.5
    # 0.5 of the 90 milk recipes and 0.5 of the 10 others.
    assert result["agreement_weighted"] == 0.5
    assert result["missed_by_catalog"] == {"eggs": 1, "gluten": 1}
    assert result["extra_in_catalog"] == {}
    assert [row["id"] for row in result["corrections"]] == ["B", "C"]
    assert result["ai_candidates"]["agree"] == 2
    text = allergens.markdown(result, sample, "h")
    assert "| `milk` | 90 | 2 | 1 | 50.0% |" in text


def test_only_checked_readable_allergen_rows_count() -> None:
    sample, ai = _allergen_sample()
    rows = [_row("A", "milk", checked=False), _row("B", None), _row("C", "nuts"), _row("D", "null")]
    result = allergens.score(rows, sample, ai)
    assert (result["checked"], result["unchecked"], result["cannot_tell"]) == (0, 1, 1)
    assert [row["id"] for row in result["refill"]] == ["B", "C"]
    assert result["agreement_weighted"] is None
    with pytest.raises(SystemExit):
        allergens.score(rows[:3], sample, ai)


def test_manual_check_rate_errors_and_unsure() -> None:
    sample = {
        "release": "v",
        "seed": 1,
        "size": 4,
        "recipes": [{"id": key, "course": "main"} for key in "ABCD"],
    }
    rows = [
        {"id": "A", "title": "A", "verdicts": ["对", "对", "对"], "note": None, "checked": True},
        {"id": "B", "title": "B", "verdicts": ["错", "错", "对"], "note": "no filling", "checked": True},
        {"id": "C", "title": "C", "verdicts": ["对", "看不出", "对"], "note": None, "checked": True},
        {"id": "D", "title": "D", "verdicts": ["对", "", "对"], "note": None, "checked": True},
    ]
    result = manual.score(rows, sample)
    assert (result["checked"], result["correct"], result["rate"]) == (2, 1, 0.5)
    assert result["errors_by_check"]["菜谱完整"] == {"recipes": 1, "share_of_errors": 0.5}
    assert result["errors_by_check"]["份量正常"] == {"recipes": 0, "share_of_errors": 0.0}
    assert [row["id"] for row in result["unsure"]] == ["C"]
    assert [row["id"] for row in result["refill"]] == ["D"]
    assert "target 95.0%: not met" in manual.markdown(result, sample, "h")
