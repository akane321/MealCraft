from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture_cold_storage_snapshot as capture  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cold_storage"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseSearchTest(unittest.TestCase):
    def test_a_results_page_gives_its_products_across_split_flight_chunks(self):
        count, products = capture.parse_search(page("search_results.html"))
        self.assertEqual((count, len(products)), (5, 5))
        self.assertTrue(all("productId" in item and "inventoryStatus" in item for item in products))

    def test_the_no_results_page_is_a_no_match_not_an_error(self):
        self.assertEqual(capture.parse_search(page("search_empty.html")), (0, []))

    def test_a_page_with_neither_is_schema_drift(self):
        with self.assertRaises(capture.ProductSchemaDriftError):
            capture.parse_search("<html><body>Please verify you are human</body></html>")

    def test_a_product_missing_a_required_field_is_schema_drift(self):
        bad = 'self.__next_f.push([1,"{\\"initialProducts\\":[{\\"productId\\":1}]}"])'
        with self.assertRaises(capture.ProductSchemaDriftError):
            capture.parse_search(f"<script>{bad}</script>")

    def test_trim_keeps_raw_prices_and_weight_for_a_weighted_item(self):
        _, products = capture.parse_search(page("search_weighted.html"))
        weighted = next(item for item in products if item["averageWeight"])
        trimmed = capture.trim_product(weighted)
        self.assertEqual(trimmed["product_id"], str(weighted["productId"]))
        self.assertEqual(trimmed["url"], f"https://coldstorage.com.sg/product/{weighted['slug']}")
        self.assertEqual(trimmed["average_weight"], weighted["averageWeight"])
        self.assertEqual((trimmed["price"], trimmed["promo_price"]), (weighted["price"], weighted["promoPrice"]))
        self.assertIsInstance(trimmed["in_stock"], bool)

    def test_plausible_needs_every_query_word_in_one_name(self):
        products = [{"name": "Aurora Premium Salmon Portion Norway 420g"}, {"name": "Smoked Salmon 85g"}]
        self.assertTrue(capture.plausible("fresh salmon", [{"name": "Fresh Salmon Fillet"}]))
        self.assertTrue(capture.plausible("salmon portions", products))
        self.assertFalse(capture.plausible("fresh salmon", products))
        self.assertFalse(capture.plausible("salmon", []))


class FollowUpTest(unittest.TestCase):
    def test_shopper_forms_drop_qualifiers_singularise_and_split_alternatives(self):
        self.assertEqual(capture.shopper_forms("dried onion flakes"), ["onion flakes", "onion flake"])
        self.assertEqual(capture.shopper_forms("mayonnaise or salad dressing"), ["mayonnaise", "salad dressing"])
        self.assertEqual(capture.shopper_forms("chard"), ["swiss chard"])
        self.assertEqual(capture.shopper_forms("sumac"), [])

    def test_a_qualifier_only_name_is_kept(self):
        self.assertNotIn("", capture.shopper_forms("fresh"))

    def test_follow_up_queries_skip_tried_ones_ignore_case_and_stop_at_three(self):
        again = ["Dill weed", "dried dill", "fresh dill"]
        self.assertEqual(capture.follow_up_queries("dill", again, {"dill"}), ["Dill weed", "dried dill", "fresh dill"])
        self.assertEqual(capture.follow_up_queries("dill", again, {"dill weed"}), ["dill", "dried dill", "fresh dill"])
        self.assertEqual(capture.follow_up_queries("dill", ["dill"], {"dill"}), [])

    def test_the_canonical_name_comes_first_then_the_simpler_form(self):
        self.assertEqual(
            capture.follow_up_queries("ground sumac", ["sumac spice"], set()), ["ground sumac", "sumac", "sumac spice"]
        )

    def test_breadth_first_puts_every_first_query_before_any_second(self):
        plan = [("ING_A", ["a1", "a2", "a3"]), ("ING_B", ["b1"]), ("ING_C", ["c1", "c2"])]
        self.assertEqual(
            capture.breadth_first(plan),
            [("ING_A", "a1"), ("ING_B", "b1"), ("ING_C", "c1"), ("ING_A", "a2"), ("ING_C", "c2"), ("ING_A", "a3")],
        )


if __name__ == "__main__":
    unittest.main()
