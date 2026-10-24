"""The review batch for the frozen model batch and the owner's own role decisions (owner 2026-10-24).

The batch holds the reviewer's table, an unreviewed AI estimate imported only where the rules leave a field open, and
the frozen fields the rules decide; the planner reads neither before the owner accepts the batch.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.paths import repository_root
from app.data import recipe_tags, tag_files
from app.data.recipe_tags import Dish, Line, rule_tags
from app.planning import product_path
from app.planning.meal_composition import meal_role_of, unreviewed

SCRIPTS = repository_root() / "data-engineering/scripts"
pytestmark = pytest.mark.skipif(
    not (SCRIPTS / "import_review_table.py").is_file(),
    reason="Repository-only review scripts are not shipped in the backend image.",
)


def script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


table = script("import_review_table") if (SCRIPTS / "import_review_table.py").is_file() else None
REVIEW = recipe_tags.REVIEW_TABLE_BATCH


def dish(key: str, title: str, course: str, lines: list[tuple[str, float]], **nutrition) -> Dish:
    values = {"kcal": 400.0, "fat_g": 15.0, "sugar_g": 5.0, "carbohydrate_g": 40.0} | nutrition
    return Dish(key, title, course, "chinese", 4, lines=[Line(n, g, None) for n, g in lines], steps="Bake.", **values)


# A baked good whose role the rules leave open (its sources, [], they decide), and a soup whose role the rules
# decide (one_bowl) and whose unnamed meat leaves its sources open.
CRESCENTS = dish("RCP2_T1", "Swedish Crescents", "baked_good", [("butter", 227), ("flour", 218.8), ("pecan", 119)])
CRESCENTS.sugar_g, CRESCENTS.carbohydrate_g = 12.0, 50.0
RAMEN = dish("RCP2_T2", "Ramen Soup", "soup", [("ramen", 85), ("water", 474), ("egg", 50), ("meat", 17.5)])
WRAPS = dish("RCP2_A84B4E56257C", "Asian Wraps", "main", [("rice_paper", 96), ("chicken_breast", 907)])


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
    assert table.code("one_bowl（一碗饭（自带主食））") == "one_bowl"  # nested brackets
    assert table.code("pork（猪）,beef（牛）") == ["beef", "pork"]
    assert table.code("pork，beef") == table.code("pork、beef（牛）") == ["beef", "pork"]  # full-width separators
    assert table.code("egg（蛋）") == ["egg"]
    assert table.code("true（是）") is True and table.code("false") is False and table.code(True) is True
    assert table.code("[]（没有主要蛋白）") == []
    assert table.code("null（未知/不放行）") is None and table.code("null") is None
    assert table.code("被规则挡住 → staple") == "staple"
    assert table.code(None) is table.SKIP and table.code("  ") is table.SKIP
    assert table.code("被规则挡住 → 待组长定") is table.SKIP
    assert table.code("是") == "是" and not table.valid("contains_staple", table.code("是"))
    assert not table.valid("meal_role", table.code("snak")) and not table.valid("protein_sources", table.code("porc"))


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


# --- the sample and its accuracy ---------------------------------------------------------------------------


def test_the_sample_is_fixed_stratified_and_takes_every_protein_only_recipe():
    accepted = {f"R{i:03d}": {"meal_role": ["dessert", "snack", "sauce"][i % 3]} for i in range(90)}
    accepted |= {"R900": {"protein_sources": ["egg"]}, "R901": {"protein_sources": []}}
    picked = table.draw_sample(accepted)
    assert picked == table.draw_sample(accepted) and len(picked) == len(set(picked))
    assert {key for stratum, key in picked if stratum == table.PROTEIN_ONLY} == {"R900", "R901"}
    assert len(picked) == table.SAMPLE_SIZE + 1  # one protein-only recipe drawn, the other added
    # The rule-decided layer: by stratum and role, at least one in each cell, the rest by size.
    rules = {f"E{i:03d}": {"stratum": "rule_equals_model", "role": "staple"} for i in range(120)}
    rules |= {f"F{i:03d}": {"stratum": "rule_equals_model", "role": table.PROTEIN_ONLY} for i in range(10)}
    rules |= {f"D{i:03d}": {"stratum": "rule_differs_from_model", "role": "vegetable"} for i in range(20)}
    rules |= {"G000": {"stratum": "rule_differs_from_model", "role": "sauce"}}
    drawn = table.draw_rule_sample(rules)
    assert drawn == table.draw_rule_sample(rules) and len(drawn) == table.RULE_SAMPLE_SIZE
    cells = Counter((stratum, role) for stratum, role, _ in drawn)
    assert cells == {
        ("rule_equals_model", "staple"): 11,
        ("rule_equals_model", table.PROTEIN_ONLY): 1,
        ("rule_differs_from_model", "vegetable"): 2,
        ("rule_differs_from_model", "sauce"): 1,
    }
    # More cells than the sample size: one in each, none dropped.
    many = {f"H{i:02d}": {"stratum": "rule_equals_model", "role": f"role{i:02d}"} for i in range(20)}
    assert len(table.draw_rule_sample(many)) == 20


def test_accuracy_is_by_stratum_and_counts_only_readable_rows_checked_in_person():
    accuracy = script("review_table_accuracy")
    a = {"meal_role": "dessert", "contains_staple": False}
    b = {"protein_sources": ["egg"]}
    sample = {
        "recipes": [
            {"id": "A", "layer": "table", "stratum": "dessert", "values": a},
            {"id": "B", "layer": "rule_decided", "stratum": "rule_differs_from_model", "values": b},
        ]
    }
    rows = [
        {"id": "A", "field": "meal_role", "value": "snack（小吃）", "checked": True},
        {"id": "A", "field": "contains_staple", "value": "否", "checked": True},  # 是/否 is not a code
        {"id": "B", "field": "protein_sources", "value": "egg，", "checked": True},  # a full-width comma reads
    ]
    result = accuracy.accuracy(rows, sample)
    groups = result["groups"]
    expected = {"rows": 2, "checked": 1, "agree": 0, "unchecked": 0, "checked_without_value": 0, "unrecognized": 1}
    assert groups["table"] == expected | {"accuracy": 0.0}
    assert groups["rule_decided"]["agree"] == groups["rule_differs_from_model"]["agree"] == 1
    assert groups["all"]["checked"] == 2 and groups["all"]["unrecognized"] == 1
    assert [row["field"] for row in result["unrecognized"]] == ["contains_staple"]
    rows[2]["checked"] = False
    assert accuracy.accuracy(rows, sample)["groups"]["rule_decided"]["unchecked"] == 1
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


def estimate(method: str, batch: str = REVIEW, reviewed: bool = False) -> dict:
    return {"method": method, "batch": batch, "reviewed": reviewed}


def test_the_owner_then_the_rules_then_the_table_then_the_frozen_value(monkeypatch):
    # The baked good's role is open: the table's lands. Its sources the rules decide: the rule's value replaces the
    # frozen model value, in the review batch, and the table's sources are not taken.
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "dessert", "protein_sources": ["egg"]})
    assert entry["meal_role"] == "dessert" and entry["contains_staple"] is False
    assert entry["estimated"]["meal_role"] == entry["estimated"]["contains_staple"] == estimate("llm")
    assert entry["protein_sources"] == [] and entry["estimated"]["protein_sources"] == estimate("rule")
    # A role outside the reviewer's options keeps the frozen value.
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "sauce"})
    assert entry["meal_role"] == "protein_main"
    assert entry["estimated"]["meal_role"] == estimate("llm", recipe_tags.LLM_BATCH)
    # The soup's role is the rules' (one_bowl) over the frozen value and the table; its open sources take the table's.
    entry = built(monkeypatch, RAMEN, {"meal_role": "soup", "protein_sources": ["egg"]})
    assert (entry["meal_role"], entry["contains_staple"]) == ("one_bowl", True)
    assert entry["estimated"]["meal_role"] == estimate("rule")
    assert entry["protein_sources"] == ["egg"] and entry["estimated"]["protein_sources"] == estimate("llm")
    # An owner's dish keeps the owner's role over a frozen one, reviewed in the owner's batch; a frozen field the
    # owner did not decide follows the rules into the review batch.
    entry = built(monkeypatch, WRAPS, {"meal_role": "one_bowl"})
    assert (entry["meal_role"], entry["contains_staple"]) == ("snack", False)
    owner = estimate("rule", recipe_tags.OWNER_BATCH, True)
    assert entry["estimated"]["meal_role"] == entry["estimated"]["contains_staple"] == owner
    assert entry["protein_sources"] == ["chicken"] and entry["estimated"]["protein_sources"] == estimate("rule")


def test_a_re_run_takes_only_the_models_own_batch_for_its_earlier_answers():
    entry = {
        "meal_role": "dessert",
        "protein_sources": [],
        "estimated": {"meal_role": estimate("llm", reviewed=True), "protein_sources": estimate("llm")},
    }
    model = {"meal_role": "snack", "estimated": {"meal_role": estimate("llm", recipe_tags.LLM_BATCH)}}
    answers = recipe_tags.previous_answers({"recipes": {"A": entry, "B": model}})
    assert answers == {"B": {"meal_role": "snack"}}


def test_the_planner_reads_the_batch_only_once_the_owner_accepts_it(monkeypatch, tmp_path: Path):
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "snack"})
    # The table's role and staple, and the rule's sources, all wait in the review batch.
    assert [entry["estimated"][name]["method"] for name in recipe_tags.CRITICAL_MODEL_FIELDS] == ["llm", "llm", "rule"]
    assert unreviewed(SimpleNamespace(**entry)) and meal_role_of(SimpleNamespace(**entry)) is None
    gated = planner_view(entry)
    assert gated["meal_role"] is gated["contains_staple"] is gated["protein_sources"] is None
    # Even with the table's values accepted, the rule-decided field of the batch keeps the recipe gated.
    held = json.loads(json.dumps(entry))
    held["estimated"]["meal_role"]["reviewed"] = held["estimated"]["contains_staple"]["reviewed"] = True
    assert unreviewed(SimpleNamespace(**held))

    target = tmp_path / tag_files.RECIPE_TAGS
    target.parent.mkdir(parents=True)
    recipe_tags.write_keyed(target, {"version": recipe_tags.VERSION}, "recipes", {CRESCENTS.key: entry})
    monkeypatch.setattr(recipe_tags, "repository_root", lambda: tmp_path)
    assert recipe_tags.accept_batch(recipe_tags.LLM_BATCH) == 0  # the model's own batch is another batch
    assert recipe_tags.accept_batch(recipe_tags.RULE_BATCH) == 0  # and ordinary rule values are never accepted
    assert recipe_tags.accept_batch(REVIEW) == 3
    accepted = json.loads(target.read_text(encoding="utf-8"))["recipes"][CRESCENTS.key]
    assert all(accepted["estimated"][name]["reviewed"] for name in recipe_tags.CRITICAL_MODEL_FIELDS)
    assert not unreviewed(SimpleNamespace(**accepted)) and meal_role_of(SimpleNamespace(**accepted)) == "snack"
    read = planner_view(accepted)
    assert read["meal_role"] == "snack" and read["contains_staple"] is False and read["protein_sources"] == []
    # A re-run keeps the accepted table values reviewed while they are unchanged, and writes the accepted rule value
    # back as an ordinary rule value: the planner still reads all three.
    again = built(monkeypatch, CRESCENTS, {"meal_role": "snack"}, previous=accepted)
    assert again["estimated"]["meal_role"] == estimate("llm", reviewed=True)
    assert again["estimated"]["protein_sources"] == estimate("rule", recipe_tags.RULE_BATCH)
    assert not unreviewed(SimpleNamespace(**again)) and planner_view(again)["protein_sources"] == []


def test_the_owners_dish_decisions_override_the_rules_as_a_persons_decision():
    other = dish("RCP2_OTHER", "Asian Wraps", "main", [("rice_paper", 96), ("chicken_breast", 907)])
    assert rule_tags(other).values["meal_role"] == "protein_main"  # the rules' role for the same dish
    entry = recipe_tags.recipe_entry(rule_tags(WRAPS))
    assert entry["meal_role"] == "snack" and entry["contains_staple"] is False
    assert entry["protein_sources"] == rule_tags(other).values["protein_sources"] == ["chicken"]
    owner = estimate("rule", recipe_tags.OWNER_BATCH, True)
    assert entry["estimated"]["meal_role"] == entry["estimated"]["contains_staple"] == owner
    assert entry["estimated"]["protein_sources"]["batch"] == recipe_tags.RULE_BATCH
    assert not unreviewed(SimpleNamespace(**entry)) and meal_role_of(SimpleNamespace(**entry)) == "snack"
    assert recipe_tags.recipe_entry(rule_tags(other))["estimated"]["meal_role"]["batch"] == recipe_tags.RULE_BATCH


def build_one(monkeypatch, item: Dish, values: dict, previous: dict) -> dict:
    monkeypatch.setattr(recipe_tags, "curated_dishes", lambda: [])
    monkeypatch.setattr(recipe_tags, "release_dishes", lambda: [item])
    monkeypatch.setattr(recipe_tags, "previous_file", lambda: {"recipes": {item.key: previous}})
    monkeypatch.setattr(recipe_tags, "review_table_values", lambda: {item.key: values})
    monkeypatch.setattr(recipe_tags, "ask_model", lambda *a: pytest.fail("No model call authorized"))
    return recipe_tags.recipe_entry(recipe_tags.build(False, 0)["tagged"][0][1], previous)


def kolache_build(monkeypatch, values: dict, previous: dict) -> dict:
    """A baked good whose egg the rules count as protein when its role is open, frozen as a model dessert."""
    return build_one(monkeypatch, KOLACHE, values, previous)


KOLACHE = dish("RCP2_T3", "Quick Kolache", "baked_good", [("flour", 250), ("butter", 113), ("egg", 100), ("sugar", 50)])
KOLACHE.sugar_g, KOLACHE.carbohydrate_g = 12.0, 50.0


@pytest.mark.parametrize("values", [{"meal_role": "dessert"}, {}], ids=["table dessert", "frozen dessert"])
def test_a_dessert_has_no_main_protein_and_a_re_run_after_acceptance_is_stable(monkeypatch, tmp_path, values):
    assert rule_tags(KOLACHE).values["meal_role"] is None and rule_tags(KOLACHE).values["protein_sources"] == ["egg"]
    frozen = recipe_tags.recipe_entry(rule_tags(KOLACHE))
    frozen |= {"meal_role": "dessert", "contains_staple": False, "protein_sources": []}
    for name in recipe_tags.CRITICAL_MODEL_FIELDS:
        frozen["estimated"][name] = estimate("llm", recipe_tags.LLM_BATCH)
    entry = kolache_build(monkeypatch, values, frozen)
    # The rules' own invariant on the final role, in the review batch while that role waits or is the batch's.
    assert entry["meal_role"] == "dessert" and entry["protein_sources"] == []
    assert entry["estimated"]["protein_sources"] == estimate("rule")
    assert kolache_build(monkeypatch, values, entry) == entry

    target = tmp_path / tag_files.RECIPE_TAGS
    target.parent.mkdir(parents=True)
    recipe_tags.write_keyed(target, {"version": recipe_tags.VERSION}, "recipes", {KOLACHE.key: entry})
    monkeypatch.setattr(recipe_tags, "repository_root", lambda: tmp_path)
    recipe_tags.accept_batch(REVIEW)
    accepted = json.loads(target.read_text(encoding="utf-8"))["recipes"][KOLACHE.key]
    again = kolache_build(monkeypatch, values, accepted)
    assert again == accepted == kolache_build(monkeypatch, values, again)  # no flip between rule and model
    assert again["estimated"]["protein_sources"] == estimate("rule", reviewed=True)
    # Once the role is an ordinary rule value, so is the invariant's.
    sauce = dish("RCP2_T4", "Lemon Sauce", "sauce_condiment", [("egg", 50), ("lemon_juice", 60)])
    owned = build_one(monkeypatch, sauce, {}, {})
    assert owned["protein_sources"] == [] and owned["estimated"]["protein_sources"] == estimate(
        "rule", recipe_tags.RULE_BATCH
    )


def test_a_table_value_comes_from_decisions_json_alone(monkeypatch):
    entry = built(monkeypatch, CRESCENTS, {"meal_role": "snack"})
    assert entry["meal_role"] == "snack" and entry["estimated"]["meal_role"] == estimate("llm")
    # Taken out of decisions.json, the field is untagged again, not the old table value carried on.
    again = built(monkeypatch, CRESCENTS, {}, previous=entry)
    assert again["meal_role"] is again["contains_staple"] is None
    assert "meal_role" not in again["estimated"] and "contains_staple" not in again["estimated"]


def test_the_committed_tag_file_carries_the_owners_decisions_and_the_gated_batch():
    entries = json.loads((repository_root() / tag_files.RECIPE_TAGS).read_text(encoding="utf-8"))["recipes"]
    owner = {
        k for k, e in entries.items() if e["estimated"].get("meal_role", {}).get("batch") == recipe_tags.OWNER_BATCH
    }
    assert owner == set(recipe_tags.OWNER_ROLES)
    for key in owner:
        assert entries[key]["meal_role"] == recipe_tags.OWNER_ROLES[key]
        assert entries[key]["contains_staple"] is (recipe_tags.OWNER_ROLES[key] in {"one_bowl", "staple"})
        assert not unreviewed(SimpleNamespace(**entries[key])), key  # the owner's decisions are read at once
    decisions = json.loads((repository_root() / recipe_tags.REVIEW_TABLE).read_text(encoding="utf-8"))
    assert decisions["reviewed"] is False and decisions["provenance"]["personally_checked_rows"] == 0
    for key, values in decisions["accepted"].items():
        for name in recipe_tags.CRITICAL_MODEL_FIELDS:
            if name in values:
                assert entries[key][name] == values[name], (key, name)
                assert entries[key]["estimated"][name] | {"reviewed": False} == estimate("llm"), (key, name)
    # The batch is accepted as a whole or not at all; before, nothing of it is read, and after, only a recipe still
    # holding a frozen model value waits.
    held = [v for e in entries.values() for v in e["estimated"].values() if v["batch"] == REVIEW]
    states = {v["reviewed"] for v in held}
    assert len(states) == 1
    batch = {k for k, e in entries.items() if any(v["batch"] == REVIEW for v in e["estimated"].values())}
    assert batch >= set(decisions["accepted"])
    for key in batch:
        model = any(
            v["batch"] == recipe_tags.LLM_BATCH and not v["reviewed"] for v in entries[key]["estimated"].values()
        )
        assert unreviewed(SimpleNamespace(**entries[key])) is (states == {False} or model), key
    # No dessert, drink or sauce keeps a main protein, whichever part decided its role.
    assert not [
        k for k, e in entries.items() if e["meal_role"] in {"dessert", "drink", "sauce"} and e["protein_sources"]
    ]
