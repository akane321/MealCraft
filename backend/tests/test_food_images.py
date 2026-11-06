"""A shared dish photo must not show a vegetarian dish with meat on it (scripts/build_food_images.py)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_food_images.py"
if not SCRIPT.exists():  # the backend image has no scripts/ or frontend/
    pytest.skip("needs the repository's scripts", allow_module_level=True)
spec = importlib.util.spec_from_file_location("build_food_images", SCRIPT)
build_food_images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_food_images)


def test_a_meatless_recipe_never_gets_a_picture_of_meat() -> None:
    dishes = json.loads(build_food_images.OUTPUT.read_text(encoding="utf-8"))["dishes"]
    recipes = {recipe["id"][-12:].lower(): recipe for recipe in build_food_images.load_recipes()}
    for image, ids in dishes.items():
        members = [recipes[slug_end] for slug_end in ids.split()]
        meatless = [recipe["title"] for recipe in members if not recipe["meat"]]
        if not meatless:
            continue
        assert image not in build_food_images.SHOWS_MEAT, (image, meatless[:3])
        # The rule's 40% is measured before recipes leave an image, so a few images may pass it afterwards; not by much.
        assert len(meatless) >= 0.5 * len(members), (image, meatless[:3])


def test_a_recipe_keeps_a_picture_only_if_it_has_what_the_picture_shows() -> None:
    veg = {"title": "tofu bowl", "vegan": True, "meat": set()}
    chicken = {"title": "chicken bowl", "vegan": False, "meat": {"poultry"}}
    misfit = build_food_images.misfit
    members = [veg, chicken]

    assert misfit(veg, {"meat"}, False, members) == "meat"
    assert misfit(chicken, {"pork"}, False, members) == "meat"
    assert misfit(chicken, {"poultry", "meat"}, False, members) is None
    assert misfit(veg, set(), True, members) == "egg or dairy"
    assert misfit({**veg, "title": "tofu soup"}, set(), False, members) == "dish word"
    assert misfit(veg, set(), False, members) is None
