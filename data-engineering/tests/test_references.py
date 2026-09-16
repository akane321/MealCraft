from __future__ import annotations

import unittest

from mealcraft_data.references import (
    _food_similarity,
    _foodon_id,
    _foodon_match_form,
    _foodon_value,
)


class ReferenceParsingTests(unittest.TestCase):
    def test_foodon_language_suffix_is_removed(self) -> None:
        self.assertEqual(_foodon_value('"tomato food product"@en'), "tomato food product")
        self.assertEqual(_foodon_value("tomato food product@en"), "tomato food product")

    def test_foodon_uri_becomes_curie(self) -> None:
        self.assertEqual(
            _foodon_id("<http://purl.obolibrary.org/obo/FOODON_00002318>"),
            "FOODON:00002318",
        )

    def test_foodon_generic_suffix_is_removed_only_for_matching(self) -> None:
        self.assertEqual(_foodon_match_form("tomato food product"), "tomato")
        self.assertEqual(_foodon_match_form("plum tomatoes"), "plum tomato")

    def test_generic_fruit_prefers_whole_raw_food(self) -> None:
        apple_raw = _food_similarity("apple", "Apples, gala, with skin, raw")
        apple_juice = _food_similarity(
            "apple", "Apple juice, with added vitamin C, from concentrate"
        )
        banana_raw = _food_similarity("banana", "Bananas, ripe and slightly ripe, raw")
        banana_pepper = _food_similarity("banana", "Peppers, banana, seeded, raw")
        self.assertGreater(apple_raw, apple_juice)
        self.assertGreater(banana_raw, banana_pepper)


if __name__ == "__main__":
    unittest.main()
