"""v3_quality_scan on tiny synthetic recipes: one case per pattern family, hit and no-hit."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import v3_quality_scan as scan  # noqa: E402

# One ingredient with a standard piece weight per tomato / lemon, dry and cooked rice with their kcal.
INGREDIENTS = [
    {
        "canonical_name": "tomato",
        "food_group": "vegetable",
        "forms": {
            "ING_TOMATO": {"unit_grams": [{"unit": "piece", "grams": 120}], "nutrition_per_100g": {"energy_kcal": 18}}
        },
    },
    {
        "canonical_name": "lemon",
        "food_group": "fruit",
        "forms": {
            "ING_LEMON": {"unit_grams": [{"unit": "piece", "grams": 60}], "nutrition_per_100g": {"energy_kcal": 29}}
        },
    },
]
FILLER = "Cook the dish in a pot over medium heat and stir often until it is thick and smooth. "


def line(text, cid="ING_THING", name="thing", grams=100.0, q=None, unit=None):
    return {
        "original_text": text,
        "canonical_ingredient_id": cid,
        "canonical_name": name,
        "grams": grams,
        "grams_basis": "stated",
        "quantity_min": q,
        "quantity_max": q,
        "unit": unit,
        "preparation": [],
        "optional": False,
    }


def recipe(steps, lines, rid="RCP2_X", kcal=300, course="main"):
    return {
        "recipe_id": rid,
        "title": "Test dish",
        "course": course,
        "servings": 4,
        "servings_basis": "stated",
        "nutrition": {"energy_kcal": kcal},
        "ingredients": lines,
        "steps": steps,
        "origin": "wave2",
    }


def patterns(r):
    return {p for p, ids in scan.scan([r], INGREDIENTS).items() if r["recipe_id"] in ids}


class PatternFamilies(unittest.TestCase):
    def test_pantry_basics_used_but_not_listed(self):
        steps = [FILLER + "Grease the baking dish. Add 2 cups water. Season with salt and pepper."]
        found = patterns(recipe(steps, [line("1 cup flour", "ING_FLOUR", "flour")]))
        self.assertTrue({"P1a_water_quantified", "P1b_salt", "P1c_pepper", "P1d_fat_greasing"} <= found)
        listed = [
            line(x, i, n) for x, i, n in [("flour", "ING_FLOUR", "flour"), ("2 cups water", "ING_WATER", "water")]
        ]
        listed += [line("salt", "ING_SALT", "salt"), line("black pepper", "ING_BLACK_PEPPER", "black pepper")]
        listed += [line("butter", "ING_BUTTER", "butter")]
        self.assertFalse(
            patterns(recipe(steps, listed)) & {"P1a_water_quantified", "P1b_salt", "P1c_pepper", "P1d_fat_greasing"}
        )

    def test_serve_with_carrier_and_named_sauce(self):
        steps = [FILLER + "Serve over rice with tartar sauce."]
        self.assertTrue(
            {"P2_serve_carrier_not_listed", "P3_named_subrecipe_not_listed"} <= patterns(recipe(steps, [line("fish")]))
        )
        rice = [
            line("fish"),
            line("1 cup rice", "ING_RICE", "rice"),
            line("tartar sauce", "ING_TARTAR_SAUCE", "tartar sauce"),
        ]
        self.assertFalse(
            patterns(recipe(steps, rice)) & {"P2_serve_carrier_not_listed", "P3_named_subrecipe_not_listed"}
        )

    def test_standard_piece_weight_where_it_does_not_fit(self):
        tomato = line("2 cherry tomatoes", "ING_TOMATO", "tomato", grams=240.0, q=2, unit="piece")
        lemon = line("1 lemon, juiced", "ING_LEMON", "lemon", grams=60.0, q=1, unit="piece")
        found = patterns(recipe([FILLER], [tomato, lemon]))
        self.assertTrue({"P4a_mini_item_whole_weight", "P4c_juice_zest_whole_fruit_weight"} <= found)
        fixed = line("2 cherry tomatoes", "ING_TOMATO", "tomato", grams=30.0, q=2, unit="piece")
        self.assertNotIn("P4a_mini_item_whole_weight", patterns(recipe([FILLER], [fixed])))

    def test_liquid_bouillon_mapped_to_cube_and_energy_outlier(self):
        bouillon = line("2 cups chicken bouillon", "ING_BOUILLON", "bouillon", grams=480.0)
        found = patterns(recipe([FILLER], [bouillon], kcal=2000))
        self.assertTrue({"P5b_liquid_bouillon_as_cube", "P6_energy_outlier", "P6h_energy_outlier_hard_1.5x"} <= found)
        self.assertFalse(
            patterns(recipe([FILLER], [line("1 cube bouillon", "ING_BOUILLON", "bouillon", 5.0)]))
            & {"P5b_liquid_bouillon_as_cube"}
        )

    def test_ingredient_that_the_steps_never_use(self):
        used = [line("2 cups walnuts", "ING_WALNUT", "walnut", 200.0), line("1 cup oats", "ING_OATS", "oats", 90.0)]
        self.assertTrue({"P7_ingredient_never_in_steps", "P7b_two_or_more_unused"} <= patterns(recipe([FILLER], used)))
        self.assertNotIn(
            "P7_ingredient_never_in_steps", patterns(recipe([FILLER + "Fold in the walnuts and oats."], used))
        )

    def test_broken_steps(self):
        found = patterns(
            recipe([FILLER, "Place in the oven until golden and"], [line("1 cup oats", "ING_OATS", "oats")])
        )
        self.assertTrue({"P8a_oven_without_temperature", "P8c_oven_without_any_time", "P8d_truncated_steps"} <= found)
        good = recipe(
            ["Bake at 350 degrees for 20 minutes until golden brown, then cool and serve the oats."] * 2, [line("oats")]
        )
        self.assertFalse(
            patterns(good) & {"P8a_oven_without_temperature", "P8c_oven_without_any_time", "P8d_truncated_steps"}
        )
        self.assertIn("P8b_fewer_than_2_steps", patterns(recipe([FILLER], [line("oats")])))


class LoadAndReport(unittest.TestCase):
    def test_origin_and_union_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            release, before = tmp / "v3", tmp / "v2.2"
            for d in (release, before):
                d.mkdir()

            def row(rid, by="", cand=""):
                return {
                    "recipe_id": rid,
                    "title": "Dish " + rid,
                    "source": {"candidate_id": cand},
                    "enrichment": {"by": by},
                    "instructions": [{"text": FILLER + "Serve over rice."}],
                }

            (release / "recipes.jsonl").write_text(
                "\n".join(
                    json.dumps(x)
                    for x in [row("A"), row("B", "claude/akane321"), row("C", cand="recipenlg:1"), row("D")]
                )
                + "\n",
                encoding="utf-8",
            )
            (before / "recipes.jsonl").write_text(json.dumps(row("A")) + "\n", encoding="utf-8")
            (release / "ingredients.jsonl").write_text("", encoding="utf-8")
            (release / "release_manifest.json").write_text('{"release_version": "vT"}', encoding="utf-8")
            wave1 = tmp / "wave1.csv"
            with wave1.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerows([["candidate_id"], ["recipenlg:1"]])

            version, recipes, ingredients = scan.load(release, before, wave1)
            self.assertEqual(version, "vT")
            self.assertEqual(
                {r["recipe_id"]: r["origin"] for r in recipes},
                {"A": "v2.2", "B": "overquota", "C": "wave1", "D": "wave2"},
            )
            for r in recipes:  # fill what the scan reads
                r.update(course="main", nutrition={"energy_kcal": 300}, ingredients=[line("fish")])
            hits = scan.scan(recipes, ingredients)
            self.assertEqual(sorted(hits["P2_serve_carrier_not_listed"]), ["A", "B", "C", "D"])
            text = scan.report(version, recipes, hits)
            self.assertIn("| any high-precision pattern (HP) | 4 | 100.0% |", text)
            self.assertEqual(text, scan.report(version, recipes, hits))


if __name__ == "__main__":
    unittest.main()
