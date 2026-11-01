"""Price coverage by ingredient, recipe and line, from small fake mappings (docs/design/cold-storage.md)."""

import json
from types import SimpleNamespace

from app.data import price_coverage
from app.data.price_coverage import markdown, report, write


def recipe(*names: str, release: bool = True, owner: int | None = None):
    lines = [SimpleNamespace(ingredient=SimpleNamespace(normalized_name=name)) for name in names]
    return SimpleNamespace(
        release_version="v2.2" if release else None, owner_household_id=owner, recipe_ingredients=lines
    )


def mapped(status: str = "mapped", products: int = 1) -> dict:
    return {"status": status, "products": [{"external_id": "1"}] * products}


FAIRPRICE = {"flour": mapped(), "egg": mapped(), "water": mapped("not_purchased", 0), "saffron": mapped("mapped", 0)}
COLD_STORAGE = {"flour": mapped(), "buttermilk": mapped(), "ice": mapped("not_purchased", 0)}
INGREDIENTS = {"flour", "egg", "water", "ice", "buttermilk", "saffron", "yuzu", "kombu"}
RECIPES = [
    recipe("flour", "egg", "water"),  # priced at FairPrice alone: water is not bought
    recipe("flour", "buttermilk"),  # needs Cold Storage
    recipe("flour", "yuzu"),  # a line neither store prices
    recipe("flour", "yuzu", "kombu", "saffron"),
    recipe("yuzu", "kombu", release=False),  # curated: not counted
    recipe("yuzu", owner=3),  # a household's own: not counted
]


def test_ingredients_are_counted_without_the_not_purchased_ones() -> None:
    ingredients = report(RECIPES, INGREDIENTS, FAIRPRICE, COLD_STORAGE)["ingredients"]

    assert ingredients["released"] == 8
    assert ingredients["not_purchased"] == ["ice", "water"]
    assert ingredients["total"] == 6  # flour egg buttermilk saffron yuzu kombu
    assert ingredients["fairprice"] == 2  # a mapped entry with no product is not a price
    assert ingredients["cold_storage_only"] == 1  # flour is at both stores: FairPrice's
    assert ingredients["combined"] == 3
    assert ingredients["combined_share"] == 0.5
    assert ingredients["target"] == 0.9
    assert ingredients["target_met"] is False


def test_the_target_is_met_at_ninety_percent_either_store() -> None:
    names = {f"item{i}" for i in range(9)}
    covered = {name: mapped() for name in names}
    result = report([], names | {"tenth"}, covered, {"tenth": mapped()})["ingredients"]

    assert (result["total"], result["combined"], result["target_met"]) == (10, 10, True)
    assert report([], names | {"tenth", "eleventh"}, covered, {"tenth": mapped()})["ingredients"]["target_met"] is True
    assert report([], names | {"a", "b"}, covered, {})["ingredients"]["target_met"] is False


def test_recipes_and_lines_are_counted_over_release_recipes_only() -> None:
    result = report(RECIPES, INGREDIENTS, FAIRPRICE, COLD_STORAGE)

    assert result["recipes"] == {
        "total": 4,
        "fairprice": 1,
        "combined": 2,
        "fairprice_share": 0.25,
        "combined_share": 0.5,
    }
    # 2 + 2 + 2 + 4 bought lines (water is not one). FairPrice prices flour and egg, flour, flour and flour
    # (saffron has no product): 5. Cold Storage adds the buttermilk: 6.
    assert (result["lines"]["total"], result["lines"]["fairprice"], result["lines"]["combined"]) == (10, 5, 6)


def test_the_most_used_unpriced_ingredients_come_most_used_first() -> None:
    unpriced = report(RECIPES, INGREDIENTS, FAIRPRICE, COLD_STORAGE)["unpriced"]

    assert unpriced == [
        {"ingredient": "yuzu", "recipes": 2},
        {"ingredient": "kombu", "recipes": 1},
        {"ingredient": "saffron", "recipes": 1},
    ]


def test_the_list_stops_at_twenty() -> None:
    names = {f"item{i:02d}" for i in range(30)}
    unpriced = report([recipe(*sorted(names))], names, {}, {})["unpriced"]

    assert len(unpriced) == 20
    assert unpriced[0] == {"ingredient": "item00", "recipes": 1}


def test_the_report_opens_with_its_title_and_scope_and_writes_both_files(tmp_path) -> None:
    result = report(RECIPES, INGREDIENTS, FAIRPRICE, COLD_STORAGE)
    result["sources"] = {"products/fairprice-v2-snapshot.json": "abc", "products/cold-storage-v1-snapshot.json": "def"}

    text = markdown(result)
    first = text.splitlines()
    assert first[0] == "# Price coverage"
    assert first[1] == ""
    assert first[2].startswith("> Scope:")
    assert "3 of 6 bought ingredients are priced (50.0%); the target of 90.0% is not met." in text
    assert "| yuzu | 2 |" in text

    write(result, tmp_path / "out")
    assert (tmp_path / "out/latest.md").read_text(encoding="utf-8") == text
    assert json.loads((tmp_path / "out/latest.json").read_text(encoding="utf-8")) == result
    assert b"\r" not in (tmp_path / "out/latest.md").read_bytes()


def test_the_snapshot_digests_ignore_line_endings(tmp_path, monkeypatch) -> None:
    (tmp_path / "products").mkdir()
    (tmp_path / "products/fairprice-v2-snapshot.json").write_bytes(b'{"a": 1}\r\n')
    (tmp_path / "products/cold-storage-v1-snapshot.json").write_bytes(b'{"a": 1}\n')
    monkeypatch.setattr("app.data.halal_pool.data_root", lambda: tmp_path)

    assert price_coverage.sha256("products/fairprice-v2-snapshot.json") == price_coverage.sha256(
        "products/cold-storage-v1-snapshot.json"
    )
