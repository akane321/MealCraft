from __future__ import annotations

import unittest

from mealcraft_data.servings import extract_servings


class ServingsExtractionTests(unittest.TestCase):
    def test_serves_n_is_extracted(self) -> None:
        result = extract_servings("Chill until firm. Serves 8.")
        self.assertEqual(result.value, 8)
        self.assertEqual(result.basis, "stated_exact")

    def test_makes_n_servings_is_extracted(self) -> None:
        result = extract_servings("Bake 20 minutes. Makes 6 servings.")
        self.assertEqual(result.value, 6)
        self.assertEqual(result.basis, "stated_exact")

    def test_yield_label_is_extracted(self) -> None:
        result = extract_servings("Stir well. Yield: 100 servings.")
        self.assertEqual(result.value, 100)
        self.assertEqual(result.basis, "stated_exact")

    def test_range_is_extracted_as_lower_bound(self) -> None:
        result = extract_servings("Bake until done. Serves 10 to 12.")
        self.assertEqual(result.value, 10)
        self.assertEqual(result.basis, "range_lower_bound")

    def test_hyphen_range_is_extracted_as_lower_bound(self) -> None:
        result = extract_servings("Serves 4-6 people.")
        self.assertEqual(result.value, 4)
        self.assertEqual(result.basis, "range_lower_bound")

    def test_makes_range_servings_is_extracted_as_lower_bound(self) -> None:
        result = extract_servings("Cool completely. Makes 8 to 10 servings.")
        self.assertEqual(result.value, 8)
        self.assertEqual(result.basis, "range_lower_bound")

    def test_descending_range_is_rejected_not_guessed(self) -> None:
        # "Serves 12 to 10" is not a sane range; do not silently swap it.
        self.assertIsNone(extract_servings("Serves 12 to 10."))

    def test_yield_of_pieces_is_not_a_serving_count(self) -> None:
        self.assertIsNone(extract_servings("Cool and cut. Makes about 24 pieces."))

    def test_yield_of_volume_is_not_a_serving_count(self) -> None:
        self.assertIsNone(extract_servings("Add water to make 2 cups."))

    def test_embedded_verb_without_a_number_is_not_extracted(self) -> None:
        self.assertIsNone(extract_servings("If desired, serve over rice."))

    def test_no_mention_returns_none(self) -> None:
        self.assertIsNone(extract_servings("Mix well and bake at 350 degrees."))

    def test_implausible_count_is_rejected(self) -> None:
        self.assertIsNone(extract_servings("Serves 0."))
        self.assertIsNone(extract_servings("Serves 5000."))

    def test_implausible_range_is_rejected(self) -> None:
        self.assertIsNone(extract_servings("Serves 10 to 5000."))

    def test_large_batch_count_is_plausible(self) -> None:
        # Punch-bowl / party recipes legitimately serve large groups.
        result = extract_servings("Add the ginger ale. Serves 100 people.")
        self.assertEqual(result.value, 100)
        self.assertEqual(result.basis, "stated_exact")


if __name__ == "__main__":
    unittest.main()
