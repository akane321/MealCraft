"""The ingredient hierarchy: what an exclusion removes, and the rules its three authors must keep."""

import json

from app.data.ingredient_hierarchy import FILES, GROUPS_FILE, empty_groups, load

ALCOHOL = {"group:alcohol": {"description": "Drinks and cooking liquids with alcohol.", "serves": "No alcohol."}}


RELEASE = [
    ("ING_PORK", "pork", "protein"),
    ("ING_BACON", "bacon", "protein"),
    ("ING_BACON_GREASE", "bacon grease", "fat"),
    ("ING_TOFU", "tofu", "protein"),
    ("ING_TOMATO", "tomato", "vegetable"),
    ("ING_MILK", "milk", "dairy"),
    ("ING_ALMOND", "almond", "protein"),
    ("ING_ALMOND_MILK", "almond milk", "plant_milk"),
    ("ING_SAKE", "sake", "beverage"),
]
CURATED = ["firm_tofu", "cherry_tomato", "milk"]


def catalog(root):
    release = root / "data-engineering/data/release/v2.1"
    release.mkdir(parents=True)
    release.joinpath("ingredients.jsonl").write_text(
        "\n".join(
            json.dumps({"ingredient_id": i, "canonical_name": n, "food_group": g, "allergens": []})
            for i, n, g in RELEASE
        ),
        encoding="utf-8",
    )
    release.joinpath("recipes.jsonl").write_text(
        json.dumps(
            {"title": "Stew", "ingredients": [{"canonical_ingredient_id": "ING_PORK", "original_text": "pork"}]}
        ),
        encoding="utf-8",
    )
    (root / "data/recipes").mkdir(parents=True)
    (root / "data/recipes/recipes.json").write_text(
        json.dumps([{"title": "Bowl", "ingredients": [{"ingredient": "firm_tofu"}]}]), encoding="utf-8"
    )
    (root / "data/ingredients/hierarchy").mkdir(parents=True)
    (root / "data/ingredients/hierarchy" / GROUPS_FILE).write_text(
        json.dumps({"schema_version": "ingredient-hierarchy-v1", "groups": ALCOHOL}), encoding="utf-8"
    )
    (root / "data/ingredients/ingredients.json").write_text(
        json.dumps([{"normalized_name": n, "display_name": n} for n in CURATED]), encoding="utf-8"
    )
    return root


def write(root, package, entries):
    document = {"schema_version": "ingredient-hierarchy-v1", "package": package, "entries": entries}
    (root / "data/ingredients/hierarchy" / FILES[package]).write_text(json.dumps(document), encoding="utf-8")


def entry(*parents, reason="a reason long enough to say what it is", not_parents=()):
    return {
        "parents": [{"id": i, "relation": r} for i, r in parents],
        "not_parents": list(not_parents),
        "reason": reason,
    }


def valid(root):
    write(
        root,
        "WP1",
        {
            "firm_tofu": entry(("tofu", "variety"), reason="firm tofu is one kind of tofu, pressed"),
            "cherry_tomato": entry(("tomato", "variety"), reason="a small variety of tomato"),
        },
    )
    write(
        root,
        "WP2",
        {
            "bacon": entry(("pork", "made_from"), reason="cured and smoked pork belly"),
            "bacon_grease": entry(("bacon", "made_from"), reason="the fat rendered out of frying bacon"),
            "sake": entry(("group:alcohol", "variety"), reason="Japanese rice wine, about 15% alcohol"),
        },
    )
    write(
        root,
        "WP3",
        {"almond_milk": entry(("almond", "made_from"), not_parents=["milk"], reason="a drink of ground almonds")},
    )
    return load(root)


def test_excluding_a_food_excludes_all_that_belongs_to_it_and_never_climbs(tmp_path):
    hierarchy = valid(catalog(tmp_path))

    assert hierarchy.errors == []
    assert hierarchy.expand(["pork"]) == {"pork", "bacon", "bacon_grease"}
    assert hierarchy.expand(["tofu"]) == {"tofu", "firm_tofu"}
    assert hierarchy.expand(["cherry_tomato"]) == {"cherry_tomato"}  # not every tomato
    assert hierarchy.expand(["group:alcohol"]) == {"group:alcohol", "sake"}
    assert "almond_milk" not in hierarchy.expand(["milk"])  # a look-alike, decided not to be milk


def test_one_food_under_two_names_is_excluded_by_either(tmp_path):
    root = catalog(tmp_path)
    valid(root)
    write(root, "WP1", {"firm_tofu": entry(("tofu", "same"), reason="the curated catalog's name for tofu")})

    hierarchy = load(root)

    assert hierarchy.expand(["tofu"]) == {"tofu", "firm_tofu"}
    assert hierarchy.expand(["firm_tofu"]) == {"tofu", "firm_tofu"}


def errors_after(tmp_path, package, entries):
    root = catalog(tmp_path)
    valid(root)
    write(root, package, entries)
    return "\n".join(load(root).errors)


def test_a_look_alike_must_be_decided(tmp_path):
    errors = errors_after(tmp_path, "WP3", {"almond_milk": entry(("almond", "made_from"))})

    assert "contains 'milk'" in errors


def test_ids_belong_to_one_package_and_must_exist(tmp_path):
    assert "belongs to WP2" in errors_after(tmp_path, "WP3", {"milk": entry(reason="cow's milk, the base of dairy")})
    assert "neither an ingredient id nor a declared group" in errors_after(
        tmp_path / "b", "WP1", {"firm_tofu": entry(("bean_curd", "variety"))}
    )


def test_a_template_reason_is_refused(tmp_path):
    same = "belongs to the family its name says it does"
    errors = errors_after(
        tmp_path,
        "WP2",
        {
            "bacon": entry(("pork", "made_from"), reason=same),
            "bacon_grease": entry(("bacon", "made_from"), reason=same),
            "pork": entry(reason=same),
            "tofu": entry(reason=same),
            "sake": entry(("group:alcohol", "variety"), reason="rice wine"),
        },
    )

    assert "used 4 times" in errors
    assert "at least 20 characters" in errors  # "rice wine"


def test_cycles_are_refused_and_empty_groups_are_reported(tmp_path):
    root = catalog(tmp_path)
    valid(root)
    write(
        root,
        "WP2",
        {
            "bacon": entry(("bacon_grease", "made_from"), reason="deliberately wrong, to make a loop"),
            "bacon_grease": entry(("bacon", "made_from"), reason="the fat rendered out of frying bacon"),
            "sake": entry(reason="Japanese rice wine, about 15% alcohol"),
        },
    )

    hierarchy = load(root)

    assert any(error.startswith("cycle:") for error in hierarchy.errors)
    assert empty_groups(hierarchy) == ["group:alcohol"]


def test_groups_are_declared_only_in_the_shared_file(tmp_path):
    root = catalog(tmp_path)
    valid(root)
    path = root / "data/ingredients/hierarchy" / FILES["WP2"]
    path.write_text(path.read_text(encoding="utf-8").replace('"entries"', '"groups": {}, "entries"'), encoding="utf-8")

    assert any("groups are declared in groups.json" in error for error in load(root).errors)
