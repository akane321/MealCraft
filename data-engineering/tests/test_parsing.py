from __future__ import annotations

import unittest
from pathlib import Path

from mealcraft_data.config import load_config
from mealcraft_data.parsing import parse_ingredient

ROOT = Path(__file__).resolve().parents[1]


class IngredientParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT)

    def test_mixed_fraction_unit_and_preparation(self) -> None:
        result = parse_ingredient(
            "1 1/2 cups uncooked rice", self.config, source_ner=["rice"]
        )
        self.assertEqual(result.quantity_min, 1.5)
        self.assertEqual(result.quantity_max, 1.5)
        self.assertEqual(result.unit_normalized, "cup")
        self.assertEqual(result.canonical_ingredient_id, "ING_RICE")
        self.assertIn("uncooked", result.preparation)
        self.assertTrue(result.source_ner_match)

    def test_unicode_fraction(self) -> None:
        result = parse_ingredient("½ onion, finely chopped", self.config)
        self.assertEqual(result.quantity_min, 0.5)
        self.assertEqual(result.canonical_ingredient_id, "ING_ONION")
        self.assertIn("finely chopped", result.preparation)

    def test_quantity_range_is_not_collapsed(self) -> None:
        result = parse_ingredient("1--2 tablespoons olive oil", self.config)
        self.assertEqual(result.quantity_min, 1.0)
        self.assertEqual(result.quantity_max, 2.0)
        self.assertIn("quantity_range", result.review_reasons)

    def test_hyphenated_mixed_number_is_not_a_range(self) -> None:
        result = parse_ingredient("1-1/2 teaspoons chili powder", self.config)
        self.assertEqual(result.quantity_min, 1.5)
        self.assertEqual(result.quantity_max, 1.5)
        self.assertNotIn("quantity_range", result.review_reasons)

    def test_hyphenated_mixed_number_with_real_range(self) -> None:
        result = parse_ingredient(
            "2-1/2 to 3 cups all-purpose flour", self.config
        )
        self.assertEqual(result.quantity_min, 2.5)
        self.assertEqual(result.quantity_max, 3.0)
        self.assertIn("quantity_range", result.review_reasons)

    def test_plain_integer_range_still_parses(self) -> None:
        result = parse_ingredient("2-3 cloves garlic", self.config)
        self.assertEqual(result.quantity_min, 2.0)
        self.assertEqual(result.quantity_max, 3.0)
        self.assertIn("quantity_range", result.review_reasons)

    def test_to_inside_a_word_is_not_a_range(self) -> None:
        result = parse_ingredient("4 toasted hamburger buns", self.config)
        self.assertEqual(result.quantity_min, 4.0)
        self.assertEqual(result.quantity_max, 4.0)
        self.assertNotIn("quantity_range", result.review_reasons)
        self.assertEqual(result.ingredient_text, "hamburger buns")
        self.assertIn("toasted", result.preparation)

    def test_spaced_to_range_still_parses(self) -> None:
        result = parse_ingredient("2 to 3 cups water", self.config)
        self.assertEqual(result.quantity_min, 2.0)
        self.assertEqual(result.quantity_max, 3.0)
        self.assertIn("quantity_range", result.review_reasons)

    def test_allergen_candidate(self) -> None:
        result = parse_ingredient("2 tbsp peanut butter", self.config)
        self.assertEqual(result.normalization_status, "mapped")
        self.assertIn("peanuts", result.allergens)

    def test_unknown_ingredient_is_candidate_not_fabricated_mapping(self) -> None:
        result = parse_ingredient("1 tbsp mystery curry blend", self.config)
        self.assertEqual(result.normalization_status, "candidate")
        self.assertTrue(result.canonical_ingredient_id.startswith("CAND_"))
        self.assertIn("unmapped_ingredient", result.review_reasons)

    def test_plural_alias_falls_back_to_singular(self) -> None:
        result = parse_ingredient("3 medium yellow onions, diced", self.config)
        self.assertEqual(result.normalization_status, "mapped")
        self.assertEqual(result.canonical_ingredient_id, "ING_ONION")

    def test_hyphenated_alias_normalizes(self) -> None:
        result = parse_ingredient("1 (15 oz.) can cream-style corn", self.config)
        self.assertEqual(result.normalization_status, "mapped")
        self.assertEqual(result.canonical_name, "cream style corn")

    def test_composite_salt_and_pepper_maps_to_composite(self) -> None:
        result = parse_ingredient("salt and pepper to taste", self.config)
        self.assertEqual(result.canonical_ingredient_id, "ING_SALT_AND_PEPPER")

    def test_bare_count_becomes_piece_unit(self) -> None:
        result = parse_ingredient("2 eggs", self.config)
        self.assertEqual(result.unit_normalized, "piece")
        self.assertNotIn("unit_missing_or_unknown", result.review_reasons)

    def test_capital_t_is_tablespoon_lowercase_t_is_teaspoon(self) -> None:
        tbsp = parse_ingredient("5 T unsalted butter, divided", self.config)
        self.assertEqual(tbsp.unit_normalized, "tbsp")
        tsp = parse_ingredient("1/2 t salt", self.config)
        self.assertEqual(tsp.unit_normalized, "tsp")

    def test_alternative_in_a_dropped_segment_is_still_flagged(self) -> None:
        result = parse_ingredient("1 c. cooked beef, pork or chicken", self.config)
        self.assertIn("ambiguous_alternative", result.review_reasons)

    def test_or_inside_an_informal_quantity_phrase_is_not_ambiguous(self) -> None:
        result = parse_ingredient("1 tsp. salt or to taste", self.config)
        self.assertEqual(result.ingredient_text, "salt")
        self.assertNotIn("ambiguous_alternative", result.review_reasons)

    def test_or_inside_a_fresh_or_thawed_idiom_is_not_ambiguous(self) -> None:
        result = parse_ingredient("2 c. fresh or thawed, frozen broccoli florets", self.config)
        self.assertEqual(result.ingredient_text, "broccoli")
        self.assertNotIn("ambiguous_alternative", result.review_reasons)

    def test_or_between_two_numbers_is_a_quantity_range(self) -> None:
        result = parse_ingredient("3 or 4 bananas", self.config)
        self.assertEqual(result.quantity_min, 3.0)
        self.assertEqual(result.quantity_max, 4.0)
        self.assertEqual(result.ingredient_text, "bananas")
        self.assertNotIn("ambiguous_alternative", result.review_reasons)

    def test_genuine_alternative_is_still_flagged(self) -> None:
        result = parse_ingredient("1/3 c. butter or margarine, melted", self.config)
        self.assertIn("ambiguous_alternative", result.review_reasons)

    def test_descending_range_is_swapped_to_min_lte_max(self) -> None:
        result = parse_ingredient("1/4 to 1/8 teaspoon nutmeg", self.config)
        self.assertEqual(result.quantity_min, 0.125)
        self.assertEqual(result.quantity_max, 0.25)
        self.assertIn("quantity_range", result.review_reasons)

    def test_dozen_is_a_unit_not_part_of_the_ingredient_name(self) -> None:
        result = parse_ingredient("1 dozen eggs", self.config)
        self.assertEqual(result.quantity_min, 1.0)
        self.assertEqual(result.unit_normalized, "dozen")
        self.assertEqual(result.canonical_ingredient_id, "ING_EGG")

    def test_empty_ingredient_is_unresolved(self) -> None:
        result = parse_ingredient("", self.config)
        self.assertEqual(result.normalization_status, "unresolved")
        self.assertIsNone(result.canonical_ingredient_id)


if __name__ == "__main__":
    unittest.main()

