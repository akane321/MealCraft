"""The reviewer's table as an unreviewed AI-estimated batch, and the owner's own role decisions (owner 2026-10-24)."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.paths import repository_root
from app.data import recipe_tags, tag_files
from app.data.recipe_tags import Dish, Line, rule_tags
from app.planning import product_path
from app.planning.meal_composition import meal_role_of, unreviewed


def script(name: str):
    path = repository_root() / f"data-engineering/scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


table = script("import_review_table")


def dish(key: str, title: str, course: str, lines: list[tuple[str, float]], **nutrition) -> Dish:
    values = {"kcal": 400.0, "fat_g": 15.0, "sugar_g": 5.0, "carbohydrate_g": 40.0} | nutrition
    return Dish(key, title, course, "chinese", 4, lines=[Line(n, g, None) for n, g in lines], steps="Bake.", **values)


# A baked good whose role the rules leave open, and a soup whose unnamed meat leaves its sources open.
CRESCENTS = dish("RCP2_T1", "Swedish Crescents", "baked_good", [("butter", 227), ("flour", 218.8), ("pecan", 119)])
CRESCENTS.sugar_g, CRESCENTS.carbohydrate_g = 12.0, 50.0
RAMEN = dish("RCP2_T2", "Ramen Soup", "soup", [("ramen", 85), ("water", 474), ("egg", 50), ("meat", 17.5)])


def row(field: str, decision: str, claude=None, model=None, other=None) -> dict:
    return {"id": "RCP2_X", "field": field, "decision": decision, "claude": claude, "model": model, "other": other}


def packet(role=None, staple=None, sources=None, roles=("one_bowl", "breakfast", "snack", "dessert")) -> dict:
    suggestion = {"meal_role": role, "contains_staple": staple, "protein_sources": sources}
    return {"RCP2_X": {"title": "X", "rule_suggestion": suggestion, "review_allowed_roles": list(roles)}}


def imported(rows: list[dict], current: dict) -> tuple[dict, dict]:
    accepted, skipped = table.decide(rows, current)
    return accepted.get("RCP2_X", {}), {item["field"]: item["reason"] for item in skipped}


# --- reading the workbook ----------------------------------------------------------------------------------


def test_workbook_codes_are_normalised():
    assert table.code("staple（主食）") == "staple"
    assert table.code("one_bowl（一碗饭（自带主食））") == "one_bowl"  # nested brackets: cut at the first
    assert table.code("pork（猪）,beef（牛）") == ["beef", "pork"]
    assert table.code("egg（蛋）") == ["egg"]
    assert table.code("true（是）") is True and table.code("false") is False and table.code(True) is True
    assert table.code("[]（没有主要蛋白）") == []
    assert table.code("null（未知/不放行）") is None and table.code("null") is None
    assert table.code("被规则挡住 → staple") == "staple"
    assert table.code(None) is table.SKIP and table.code("  ") is table.SKIP
    assert table.code("被规则挡住 → 待组长定") is table.SKIP


def test_a_decision_means_the_value_it_names():
    assert table.intended(row("meal_role", "同意Claude建议", claude="被规则挡住 → staple", model="snack")) == "staple"
    assert table.intended(row("meal_role", "同意模型原值", claude="staple", model="snack（小吃）")) == "snack"
    assert table.intended(row("meal_role", "改成其他值", claude="staple", other="soup")) == "soup"
    assert (
        table.intended(row("meal_role", "被规则挡住（聊天确认：完整的一餐）", claude="x", other="one_bowl"))
        == "one_bowl"
    )
    assert table.intended(row("meal_role", "聊天确认A", claude="snack（小吃）")) == "snack"
    assert table.intended(row("meal_role", "改成其他值", claude="staple")) is table.SKIP
    assert table.intended(row("meal_role", "跳过", claude="staple", other="soup")) is table.SKIP
    assert table.intended(row("meal_role", None, claude="staple")) is table.SKIP


# --- what is imported --------------------------------------------------------------------------------------


def test_a_field_the_rules_decide_keeps_the_rule_whatever_the_workbook_says():
    rows = [row("meal_role", "改成其他值", other="snack"), row("contains_staple", "改成其他值", other="false")]
    values, reasons = imported(rows, packet(role="staple", staple=True))
    assert values == {} and set(reasons.values()) == {"rule_decided_conflicts"}
    rows = [row("meal_role", "同意Claude建议", claude="staple"), row("protein_sources", "同意模型原值", model="egg")]
    values, reasons = imported(rows, packet(role="staple", staple=True, sources=["egg"]))
    assert values == {} and set(reasons.values()) == {"rule_decided_agrees"}


def test_the_owners_dish_decisions_win_over_the_workbook(monkeypatch):
    monkeypatch.setattr(table, "OWNER_ROLES", {"RCP2_X": "snack"})
    values, reasons = imported([row("meal_role", "改成其他值", other="dessert")], packet())
    assert values == {} and reasons == {"meal_role": "owner_decided"}


def test_only_open_fields_with_values_in_range_are_imported():
    rows = [
        row("meal_role", "同意模型原值", model="dessert（甜点）"),
        row("contains_staple", "同意模型原值", model="false（否）"),
        row("protein_sources", "改成其他值", other="pork,beef"),
    ]
    values, reasons = imported(rows, packet())
    assert values == {
        "title": "X",
        "meal_role": "dessert",
        "contains_staple": False,
        "protein_sources": ["pork", "beef"],
    }
    assert reasons == {}  # in the vocabulary's order, as the rules write them
    assert imported([row("protein_sources", "改成其他值", other="[]")], packet())[0]["protein_sources"] == []
    for value, reason in (("sauce", "outside_allowed_roles"), ("main_course", "invalid_value"), ("null", "left_open")):
        values, reasons = imported([row("meal_role", "改成其他值", other=value)], packet())
        assert values == {} and reasons == {"meal_role": reason}
    for value, reason in (("pork,goose", "invalid_value"), ("null", "left_open")):
        assert imported([row("protein_sources", "改成其他值", other=value)], packet())[1] == {"protein_sources": reason}
    assert imported([row("meal_role", "跳过", claude="dessert")], packet())[1] == {"meal_role": "skipped_by_reviewer"}


def test_contains_staple_follows_the_imported_role():
    one_bowl = row("meal_role", "改成其他值", other="one_bowl")
    values, _ = imported([one_bowl, row("contains_staple", "改成其他值", other="true")], packet())
    assert values["contains_staple"] is True
    values, _ = imported([one_bowl], packet())  # no staple row: it follows the role
    assert values["contains_staple"] is True
    for staple in ("false", "null"):
        values, reasons = imported([one_bowl, row("contains_staple", "改成其他值", other=staple)], packet())
        assert values == {} and reasons == {
            "meal_role": "staple_inconsistent",
            "contains_staple": "staple_inconsistent",
        }
    # A staple whose role is not imported is not imported either.
    rows = [row("meal_role", "改成其他值", other="sauce"), row("contains_staple", "改成其他值", other="false")]
    assert imported(rows, packet())[1] == {
        "meal_role": "outside_allowed_roles",
        "contains_staple": "outside_allowed_roles",
    }


def test_the_sample_is_fixed_stratified_and_counts_only_rows_checked_in_person():
    accepted = {f"R{i:03d}": {"meal_role": ["dessert", "snack", "sauce"][i % 3]} for i in range(90)}
    accepted |= {"R900": {"protein_sources": ["egg"]}}
    picked = table.draw_sample(accepted)
    assert picked == table.draw_sample(accepted) and len(picked) == table.SAMPLE_SIZE == len(set(picked))
    assert {stratum for stratum, _ in picked} == {"dessert", "snack", "sauce", "protein_sources only"}

    accuracy = script("review_table_accuracy")
    sample = {"recipes": [{"id": "A", "imported": {"meal_role": "dessert", "contains_staple": False}}]}
    rows = [
        {"id": "A", "field": "meal_role", "value": "snack（小吃）", "checked": True},
        {"id": "A", "field": "contains_staple", "value": False, "checked": False},
    ]
    result = accuracy.accuracy(rows, sample)["fields"]
    expected = {"rows": 1, "checked": 1, "agree": 0, "unchecked": 0, "checked_without_value": 0, "accuracy": 0.0}
    assert result["meal_role"] == expected
    assert result["contains_staple"]["unchecked"] == 1 and result["contains_staple"]["accuracy"] is None
    with pytest.raises(SystemExit):
        accuracy.accuracy(rows[:1], sample)


# --- the tag file and the planner --------------------------------------------------------------------------


def built(monkeypatch, item: Dish, values: dict, previous: dict | None = None) -> dict:
    """The tag file entry `build` writes for `item` with these review-table values over a frozen model entry."""
    frozen = recipe_tags.recipe_entry(rule_tags(item))
    for name in recipe_tags.CRITICAL_MODEL_FIELDS:
        frozen["estimated"][name] = {"method": "llm", "batch": recipe_tags.LLM_BATCH, "reviewed": False}
    frozen |= {"meal_role": "protein_main", "contains_staple": False, "protein_sources": ["pork", "beef"]}
    previous = previous or frozen
    monkeypatch.setattr(recipe_tags, "curated_dishes", lambda: [])
    monkeypatch.setattr(recipe_tags, "release_dishes", lambda: [item])
    monkeypatch.setattr(recipe_tags, "previous_file", lambda: {"recipes": {item.key: previous}})
    monkeypatch.setattr(recipe_tags, "review_table_values", lambda: {item.key: values})
    monkeypatch.setattr(recipe_tags, "ask_model", lambda *a: pytest.fail("No model call authorized"))
    return recipe_tags.recipe_entry(recipe_tags.build(False, 0)["tagged"][0][1], previous)


def planner_view(entry: dict) -> dict:
    recipe = SimpleNamespace(**entry, cuisine="chinese", recipe_ingredients=[])
    return product_path.recipe_tags(recipe, SimpleNamespace(ingredients=[]))


def test_the_rules_win_and_an_open_field_takes_the_table_unreviewed(monkeypatch):
    # The baked good's role is open, its sources ([]) are the rules': the table's role lands, its sources do not.
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "dessert", "protein_sources": ["egg"]})
    batch = {"method": "llm", "batch": recipe_tags.REVIEW_TABLE_BATCH, "reviewed": False}
    assert entry["meal_role"] == "dessert" and entry["contains_staple"] is False
    assert entry["estimated"]["meal_role"] == entry["estimated"]["contains_staple"] == batch
    # The rules decide its sources ([]), so the table's are not taken; the frozen model value stays frozen.
    assert entry["protein_sources"] == ["pork", "beef"]
    assert entry["estimated"]["protein_sources"]["batch"] == recipe_tags.LLM_BATCH
    # A role outside the reviewer's options keeps the frozen value.
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "sauce"})
    assert entry["meal_role"] == "protein_main" and entry["estimated"]["meal_role"]["batch"] == recipe_tags.LLM_BATCH
    # The soup's role is the rules' (one_bowl, frozen); its unknown sources are open and take the table's.
    entry = built(monkeypatch, RAMEN, {"meal_role": "soup", "protein_sources": ["egg"]})
    assert entry["meal_role"] == "protein_main" and entry["estimated"]["meal_role"]["batch"] == recipe_tags.LLM_BATCH
    assert entry["protein_sources"] == ["egg"] and entry["estimated"]["protein_sources"] == batch


def test_the_planner_ignores_the_table_until_the_owner_accepts_the_batch(monkeypatch, tmp_path: Path):
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "snack"})
    entry["estimated"]["protein_sources"] = {"method": "rule", "batch": recipe_tags.RULE_BATCH, "reviewed": False}
    entry["protein_sources"] = []  # only the table's fields wait for review
    assert unreviewed(SimpleNamespace(**entry)) and meal_role_of(SimpleNamespace(**entry)) is None
    gated = planner_view(entry)
    assert gated["meal_role"] is gated["contains_staple"] is gated["protein_sources"] is None

    target = tmp_path / tag_files.RECIPE_TAGS
    target.parent.mkdir(parents=True)
    recipe_tags.write_keyed(target, {"version": recipe_tags.VERSION}, "recipes", {CRESCENTS.key: entry})
    monkeypatch.setattr(recipe_tags, "repository_root", lambda: tmp_path)
    assert recipe_tags.accept_batch(recipe_tags.LLM_BATCH) == 0  # the model's own batch is another batch
    assert recipe_tags.accept_batch(recipe_tags.REVIEW_TABLE_BATCH) == 2
    accepted = json.loads(target.read_text(encoding="utf-8"))["recipes"][CRESCENTS.key]
    assert (
        accepted["estimated"]["meal_role"]["reviewed"] is accepted["estimated"]["contains_staple"]["reviewed"] is True
    )
    assert not unreviewed(SimpleNamespace(**accepted)) and meal_role_of(SimpleNamespace(**accepted)) == "snack"
    read = planner_view(accepted)
    assert read["meal_role"] == "snack" and read["contains_staple"] is False and read["protein_sources"] == []
    # A re-run keeps the accepted values reviewed while they are unchanged.
    again = built(monkeypatch, CRESCENTS, {"meal_role": "snack"}, previous=accepted)
    assert again["estimated"]["meal_role"] == {
        "method": "llm",
        "batch": recipe_tags.REVIEW_TABLE_BATCH,
        "reviewed": True,
    }


def test_the_owners_dish_decisions_override_the_rules_as_a_persons_decision():
    wraps = dish("RCP2_A84B4E56257C", "Asian Wraps", "main", [("rice_paper", 96), ("chicken_breast", 907)])
    other = dish("RCP2_OTHER", "Asian Wraps", "main", [("rice_paper", 96), ("chicken_breast", 907)])
    assert rule_tags(other).values["meal_role"] == "protein_main"  # the rules' role for the same dish
    entry = recipe_tags.recipe_entry(rule_tags(wraps))
    assert entry["meal_role"] == "snack" and entry["contains_staple"] is False
    assert entry["protein_sources"] == rule_tags(other).values["protein_sources"] == ["chicken"]
    owner = {"method": "rule", "batch": recipe_tags.OWNER_BATCH, "reviewed": True}
    assert entry["estimated"]["meal_role"] == entry["estimated"]["contains_staple"] == owner
    assert entry["estimated"]["protein_sources"]["batch"] == recipe_tags.RULE_BATCH
    assert not unreviewed(SimpleNamespace(**entry)) and meal_role_of(SimpleNamespace(**entry)) == "snack"
    assert recipe_tags.recipe_entry(rule_tags(other))["estimated"]["meal_role"]["batch"] == recipe_tags.RULE_BATCH


def test_the_committed_tag_file_carries_the_owners_decisions_and_the_unreviewed_table():
    entries = json.loads((repository_root() / tag_files.RECIPE_TAGS).read_text(encoding="utf-8"))["recipes"]
    owner = {
        key
        for key, entry in entries.items()
        if entry["estimated"].get("meal_role", {}).get("batch") == recipe_tags.OWNER_BATCH
    }
    assert owner == set(recipe_tags.OWNER_ROLES)
    assert {key: entries[key]["meal_role"] for key in owner} == recipe_tags.OWNER_ROLES
    assert {
        (entries[key]["contains_staple"], entries[key]["estimated"]["protein_sources"]["batch"]) for key in owner
    } == {(False, recipe_tags.RULE_BATCH)}
    decisions = json.loads((repository_root() / recipe_tags.REVIEW_TABLE).read_text(encoding="utf-8"))
    assert decisions["reviewed"] is False and decisions["provenance"]["personally_checked_rows"] == 0
    for key, values in decisions["accepted"].items():
        for name in recipe_tags.CRITICAL_MODEL_FIELDS:
            if name in values:
                assert entries[key][name] == values[name], (key, name)
                assert entries[key]["estimated"][name]["batch"] == recipe_tags.REVIEW_TABLE_BATCH, (key, name)
        assert unreviewed(SimpleNamespace(**entries[key])), key  # nothing of the table is read before acceptance
