from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_release_v2 import derive_tags, ingredient_rules  # noqa: E402
from recipe_completeness import names_meat, unlisted_allergens  # noqa: E402


def recipe(title: str, *steps: str) -> dict:
    return {"title": title, "instructions": [{"step_number": i, "text": s} for i, s in enumerate(steps, 1)]}


class CompletenessCheckTests(unittest.TestCase):
    def test_a_dish_naming_what_its_list_lacks_is_flagged(self) -> None:
        quiche = recipe("Crab Meat Quiche", "Make the crust.", "Beat the eggs with milk and fold in the crab.")
        self.assertEqual(unlisted_allergens(quiche, {"gluten"}), ["crustaceans", "eggs", "milk"])

    def test_listed_allergens_answer_the_mention(self) -> None:
        self.assertEqual(unlisted_allergens(recipe("Omelet", "Whisk the eggs."), {"eggs"}), [])
        self.assertEqual(unlisted_allergens(recipe("Toast", "Toast the bread."), {"gluten_candidate"}), [])

    def test_a_compound_keeps_the_allergen_it_carries(self) -> None:
        self.assertEqual(unlisted_allergens(recipe("Satay", "Pour over the peanut butter sauce."), set()), ["peanuts"])
        self.assertEqual(unlisted_allergens(recipe("Shake", "Blend with almond milk."), set()), ["tree_nuts"])
        self.assertEqual(unlisted_allergens(recipe("Dip", "Stir in the mayonnaise."), set()), ["eggs"])

    def test_look_alikes_are_not_the_food(self) -> None:
        for title, step in [
            ("Cookies", "Cream the sugar and shortening; add cream of tartar."),
            ("Pad Thai", "Soak the rice noodles in coconut milk."),
            ("Roast", "Butterfly the pork and add nutmeg."),
            ("Stir Fry", "Roast the spaghetti squash and eggplant."),
        ]:
            self.assertEqual(unlisted_allergens(recipe(title, step), set()), [], title)

    def test_meat_in_the_text(self) -> None:
        self.assertTrue(names_meat(recipe("Fried Rice", "Serve with chicken adobo.")))
        self.assertFalse(names_meat(recipe("Butternut Soup", "Blend the squash.")))


class RuleTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = ingredient_rules()

    def test_owner_confirmed_corrections_only_add(self) -> None:
        self.assertIn("milk", self.rules["ING_BUTTER_OR_MARGARINE"]["allergens"])
        self.assertIn("milk", self.rules["ING_MARGARINE"]["allergens"])
        self.assertIn("gluten_candidate", self.rules["ING_TORTILLA"]["allergens"])
        self.assertIn("eggs", self.rules["ING_EGG_SUBSTITUTE"]["allergens"])
        self.assertIn("fish", self.rules["ING_IMITATION_CRAB"]["allergens"])

    def test_fish_or_shellfish_is_never_vegetarian(self) -> None:
        tags, _ = derive_tags(
            [{"canonical_ingredient_id": "ING_RICE"}, {"canonical_ingredient_id": "ING_KIMCHI"}], self.rules
        )
        self.assertNotIn("vegetarian", tags)
        self.assertNotIn("vegan", tags)


if __name__ == "__main__":
    unittest.main()
